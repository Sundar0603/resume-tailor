"""
Canonicalization for Resume Planner output.

Pinning the sampling parameters makes the model *return* the same content on
every call. It does not make that content *comparable* or even ingestible:
list order drifts, priority arrives as a name where :class:`SectionPriority`
is an ``IntEnum`` and cannot parse ``"CRITICAL"`` on its own, and action
casing is inconsistent. Canonicalization removes that residual variation
before Pydantic ever sees the payload.

The transformation is idempotent: ``canonicalize(canonicalize(x))`` equals
``canonicalize(x)``.

Only recognised keys are touched, and values of an unexpected type are passed
through untouched so that Pydantic still reports the real schema error.
"""

from typing import Any, Dict, List, Optional

from src.analyzer.canonical import canonical_text

#: Fields whose order carries no meaning; sorted alphabetically and
#: deduplicated case-insensitively.
SET_LIKE_FIELDS = (
    "keywords_to_include",
    "themes_to_emphasize",
    "skills_to_add",
    "skills_to_remove",
)

#: Prose fields: cleaned like any scalar, but the terminal period is kept
#: since these are full sentences, not list items.
PROSE_FIELDS = (
    "reasoning",
    "rewrite_strategy",
    "generation_brief",
)

#: Optional scalar identity/name fields that may arrive as "", "null", etc.
#: instead of a proper JSON null.
NULLABLE_SCALAR_FIELDS = (
    "category_id",
    "project_id",
    "new_category_name",
    "rewrite_strategy",
    "generation_brief",
)

#: A small, deliberately narrow alias map for action values. Kept short on
#: purpose: an over-forgiving alias list would mask genuine prompt failures
#: instead of surfacing them as validation errors.
_ACTION_ALIASES = {
    "ADD": "GENERATE",
    "CREATE": "GENERATE",
    "DELETE": "REMOVE",
    "UPDATE": "REWRITE",
    "MODIFY": "REWRITE",
}

_PRIORITY_ALIASES = {
    "CRITICAL": 1,
    "HIGH": 2,
    "MEDIUM": 3,
    "LOW": 4,
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
}

_NULL_EQUIVALENTS = frozenset({"", "null", "none", "n/a", "na", "nil"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def canonicalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a canonical copy of a parsed planner payload.

    Parameters
    ----------
    data : dict
        The JSON object returned by the LLM, already parsed.

    Returns
    -------
    dict
        A new dictionary. The input is never mutated.
    """
    if not isinstance(data, dict):
        return data

    result = dict(data)

    if "summary_plan" in result:
        result["summary_plan"] = _canonicalize_plan(result["summary_plan"])

    for field in ("skills_plans", "experience_plans", "project_plans"):
        if field in result and isinstance(result[field], list):
            result[field] = [_canonicalize_plan(item) for item in result[field]]

    if isinstance(result.get("experience_plans"), list):
        result["experience_plans"] = _sort_by_id(
            result["experience_plans"], "experience_id"
        )
    if isinstance(result.get("project_plans"), list):
        result["project_plans"] = _sort_by_id(result["project_plans"], "project_id")
    if isinstance(result.get("skills_plans"), list):
        result["skills_plans"] = _sort_by_id(result["skills_plans"], "category_id")

    return result


# ---------------------------------------------------------------------------
# One plan entry
# ---------------------------------------------------------------------------


def _canonicalize_plan(plan: Any) -> Any:
    """Canonicalize one plan dict (summary, skill category, exp, or project)."""
    if not isinstance(plan, dict):
        return plan

    result = dict(plan)

    if "action" in result:
        result["action"] = _canonical_action(result["action"])

    if "priority" in result:
        result["priority"] = _canonical_priority(result["priority"])

    for field in PROSE_FIELDS:
        if field in result:
            result[field] = _canonical_prose(
                result[field], nullable=field in NULLABLE_SCALAR_FIELDS
            )

    for field in NULLABLE_SCALAR_FIELDS:
        if field in result and field not in PROSE_FIELDS:
            result[field] = _canonical_nullable_scalar(result[field])

    for field in SET_LIKE_FIELDS:
        if field in result:
            result[field] = _canonical_list(result[field])

    return result


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------


def _canonical_action(value: Any) -> Any:
    """Normalize action casing and apply the narrow alias map."""
    if not isinstance(value, str):
        return value
    cleaned = value.strip().upper()
    return _ACTION_ALIASES.get(cleaned, cleaned)


def _canonical_priority(value: Any) -> Any:
    """Normalize a priority name/alias to its int value; pass through otherwise."""
    if isinstance(value, str):
        key = value.strip().upper()
        if key in _PRIORITY_ALIASES:
            return _PRIORITY_ALIASES[key]
        return value
    return value


def _canonical_nullable_scalar(value: Any) -> Any:
    """Map null-equivalent strings to None; pass everything else through."""
    if value is None or not isinstance(value, str):
        return value
    cleaned = canonical_text(value)
    if cleaned is None or cleaned.casefold() in _NULL_EQUIVALENTS:
        return None
    return cleaned


def _canonical_prose(value: Any, nullable: bool) -> Any:
    """Clean a prose field, keeping its terminal period."""
    if value is None or not isinstance(value, str):
        return value

    text = value.strip()
    if nullable and text.casefold() in _NULL_EQUIVALENTS:
        return None

    # canonical_text strips the terminal period; add it back if present in
    # the source, since prose sentences should keep their punctuation.
    cleaned = canonical_text(value)
    if cleaned is None:
        return None
    if text.endswith(".") and not cleaned.endswith("."):
        cleaned = f"{cleaned}."
    return cleaned


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def _canonical_list(value: Any) -> Any:
    """Clean, deduplicate case-insensitively, and sort a list field."""
    if not isinstance(value, list):
        return value

    cleaned: List[Any] = []
    seen = set()

    for item in value:
        if not isinstance(item, str):
            cleaned.append(item)
            continue

        text = canonical_text(item)
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(text)

    if all(isinstance(item, str) for item in cleaned):
        cleaned.sort(key=lambda item: (item.casefold(), item))

    return cleaned


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def _sort_by_id(items: List[Any], id_field: str) -> List[Any]:
    """
    Sort plan entries by id, with GENERATE entries (null id) last.

    Non-dict entries and entries with a non-string id are passed through
    without reordering relative to each other, appended after the sortable
    entries, so schema validation still reports the real error.
    """
    sortable = []
    unsortable = []

    for item in items:
        if isinstance(item, dict) and (
            item.get(id_field) is None or isinstance(item.get(id_field), str)
        ):
            sortable.append(item)
        else:
            unsortable.append(item)

    sortable.sort(
        key=lambda item: (item.get(id_field) is None, item.get(id_field) or "")
    )

    return sortable + unsortable
