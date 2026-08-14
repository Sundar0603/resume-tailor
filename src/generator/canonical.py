"""
Normalisation of raw Resume Generator responses.

The Analyzer and Planner canonicalise to make their output *deterministic*.
This module has a smaller job: the Generator runs at a non-zero temperature, so
its responses carry small formatting variance — a trailing space, a stray empty
bullet, ``null`` where an empty list was meant. None of that should fail a
generation, and none of it should reach the resume.

Only shape and whitespace are touched. Wording is never rewritten here.
"""

from typing import Any, Dict, List

#: Keys whose values are lists of short strings.
_STRING_LIST_FIELDS = ("technologies", "domains", "highlights", "skills")

#: Keys whose values are single strings.
_STRING_FIELDS = ("summary", "role", "name", "type", "experience_id", "project_id")


def canonicalize_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw summary response."""
    cleaned = dict(data)
    cleaned["summary"] = _clean_text(cleaned.get("summary"))
    return cleaned


def canonicalize_experiences(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw experience response."""
    cleaned = dict(data)
    cleaned["experiences"] = [
        _clean_entity(entry) for entry in _as_list(cleaned.get("experiences"))
    ]
    return cleaned


def canonicalize_projects(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw project response."""
    cleaned = dict(data)
    cleaned["projects"] = [
        _clean_entity(entry) for entry in _as_list(cleaned.get("projects"))
    ]
    return cleaned


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> List[Any]:
    """Coerce a possibly-null container into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value: Any) -> Any:
    """Strip a string, collapsing internal runs of whitespace."""
    if not isinstance(value, str):
        return value
    return " ".join(value.split())


def _clean_string_list(value: Any) -> List[str]:
    """
    Strip every entry, dropping blanks and preserving order.

    Duplicates are removed case-insensitively, keeping the first spelling.
    The validator treats a repeated skill inside one category as an error, and
    a model listing "Python" twice is a formatting slip, not a content one.
    """
    seen = set()
    cleaned: List[str] = []
    for entry in _as_list(value):
        if not isinstance(entry, str):
            continue
        text = _clean_text(entry)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _clean_entity(entry: Any) -> Any:
    """Normalise one experience or project entry."""
    if not isinstance(entry, dict):
        return entry

    cleaned = dict(entry)
    for field in _STRING_FIELDS:
        if field in cleaned:
            cleaned[field] = _clean_text(cleaned[field])
    for field in _STRING_LIST_FIELDS:
        if field in cleaned:
            cleaned[field] = _clean_string_list(cleaned[field])
    return cleaned
