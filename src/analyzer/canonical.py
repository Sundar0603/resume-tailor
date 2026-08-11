"""
Canonicalization for Job Description Analyzer output.

Pinning the sampling parameters makes the model *return* the same content on
every call. It does not make that content *comparable*: the same extracted
facts still arrive with different list ordering, near-duplicate entries that
differ only in case, inconsistent trailing punctuation, and the occasional
skill that migrates between ``required_skills`` and ``preferred_skills``.

Canonicalization removes that residual variation, so two analyses of the same
job description are equal rather than merely equivalent.

Ordering rules:

- Set-like fields (skills, technologies, domains, nice-to-have, keywords)
  carry no meaningful order and are sorted alphabetically.
- Prose fields (responsibilities, qualifications) read as a sequence and keep
  the order in which the job description states them; they are deduplicated
  but never reordered.

The transformation is idempotent: ``canonicalize(canonicalize(x))`` equals
``canonicalize(x)``.

Only recognised keys are touched, and values of an unexpected type are passed
through untouched so that Pydantic still reports the real schema error.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

#: Fields whose order carries no meaning; sorted alphabetically.
SET_LIKE_FIELDS = (
    "required_skills",
    "preferred_skills",
    "technologies",
    "domains",
    "nice_to_have",
    "keywords",
)

#: Fields that read as prose; deduplicated but kept in job description order.
PROSE_FIELDS = (
    "responsibilities",
    "qualifications",
)

#: Free-text scalar fields.
SCALAR_FIELDS = (
    "company",
    "role",
    "seniority",
)

#: Scalars that are allowed to be absent. Models express "absent" in many
#: ways; all of them collapse to None.
NULLABLE_SCALAR_FIELDS = ("company", "seniority")

_NULL_EQUIVALENTS = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "nil",
        "unknown",
        "unspecified",
        "not mentioned",
        "not specified",
        "not stated",
        "not provided",
    }
)

_WHITESPACE = re.compile(r"\s+")
_LEADING_BULLET = re.compile(r"^[\-\*•–—·]+\s*")
#: Trailing abbreviations such as "B.S." or "Ph.D." keep their final period.
_ABBREVIATION_TAIL = re.compile(r"(?:\b[A-Za-z]\.){2,}$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def canonicalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a canonical copy of a parsed analyzer payload.

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

    for field in SCALAR_FIELDS:
        if field in result:
            result[field] = _canonical_scalar(
                result[field],
                nullable=field in NULLABLE_SCALAR_FIELDS,
            )

    for field in SET_LIKE_FIELDS:
        if field in result:
            result[field] = _canonical_list(result[field], sort=True)

    for field in PROSE_FIELDS:
        if field in result:
            result[field] = _canonical_list(result[field], sort=False)

    _remove_cross_listed_skills(result)

    return result


def canonical_text(value: Optional[str]) -> Optional[str]:
    """
    Apply the scalar text rules to an arbitrary string.

    Used by the determinism harness when comparing values across runs.
    """
    if value is None:
        return None
    return _strip_terminal_period(_clean_text(value))


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------


def _canonical_scalar(value: Any, nullable: bool) -> Any:
    """Clean a scalar field, mapping null-equivalents to None when allowed."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    cleaned = _strip_terminal_period(_clean_text(value))

    if nullable and cleaned.casefold() in _NULL_EQUIVALENTS:
        return None

    return cleaned


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def _canonical_list(value: Any, sort: bool) -> Any:
    """
    Clean, deduplicate and optionally sort a list field.

    Non-list values and non-string items are passed through untouched so
    that schema validation still reports them.
    """
    if not isinstance(value, list):
        return value

    cleaned: List[Any] = []
    seen = set()

    for item in value:
        if not isinstance(item, str):
            cleaned.append(item)
            continue

        text = _strip_terminal_period(_clean_text(item))
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(text)

    if sort and all(isinstance(item, str) for item in cleaned):
        cleaned.sort(key=lambda item: (item.casefold(), item))

    return cleaned


def _remove_cross_listed_skills(data: Dict[str, Any]) -> None:
    """
    Drop preferred skills that are already listed as required.

    Borderline skills drift between the two lists from run to run; a skill
    that is required is not also merely preferred, so the required list wins.
    """
    required = data.get("required_skills")
    preferred = data.get("preferred_skills")

    if not isinstance(required, list) or not isinstance(preferred, list):
        return

    required_keys = {
        _dedupe_key(item) for item in required if isinstance(item, str)
    }
    if not required_keys:
        return

    data["preferred_skills"] = [
        item
        for item in preferred
        if not (isinstance(item, str) and _dedupe_key(item) in required_keys)
    ]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    """
    Normalize unicode, drop bullet prefixes, and collapse whitespace.

    NFKC folds non-breaking spaces and full-width punctuation into their
    ASCII equivalents, so the whitespace collapse below sees a single
    space family regardless of what the model emitted.
    """
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    normalized = _LEADING_BULLET.sub("", normalized)
    return _strip_wrapping_quotes(normalized).strip()


def _strip_wrapping_quotes(text: str) -> str:
    """Remove a single layer of matching surrounding quotes."""
    pairs = (
        ('"', '"'),
        ("'", "'"),
        ("“", "”"),
        ("‘", "’"),
    )
    for opening, closing in pairs:
        if len(text) >= 2 and text.startswith(opening) and text.endswith(closing):
            return text[1:-1].strip()
    return text


def _strip_terminal_period(text: str) -> str:
    """
    Remove a single trailing period.

    Whether the model terminates an item with a period varies between runs.
    Abbreviations such as ``Ph.D.`` keep theirs.
    """
    if not text.endswith("."):
        return text
    if _ABBREVIATION_TAIL.search(text):
        return text
    return text[:-1].rstrip()


def _dedupe_key(text: str) -> str:
    """Return the case- and punctuation-insensitive identity of an item."""
    return _strip_terminal_period(_clean_text(text)).casefold()
