"""
JSON extraction helpers for the Job Description Analyzer.

Language models are asked to return a bare JSON object, and mostly do. The
remaining cases — a markdown code fence, a "Here is the JSON:" preamble, a
trailing sentence — are not analysis failures, but feeding them straight to
:func:`json.loads` turns a perfectly good answer into an error. Since the
same model may wrap its output on one call and not the next, tolerating the
wrapper is part of making the analyzer deterministic.

This module only locates the JSON object. It never repairs malformed JSON:
genuinely broken output must still fail loudly.
"""

from typing import Optional

_FENCE = "```"


def extract_json_object(raw: str) -> str:
    """
    Return the JSON object embedded in *raw*.

    Strips markdown code fences, then returns the first balanced ``{...}``
    span. Braces inside string literals are ignored, so a value such as
    ``"uses {braces} in text"`` does not confuse the scan.

    Parameters
    ----------
    raw : str
        The raw text returned by the LLM provider.

    Returns
    -------
    str
        The substring containing the JSON object. Returned unchanged when
        no balanced object is found, so that the caller's ``json.loads``
        raises the real parse error.
    """
    text = _strip_code_fences(raw.strip())
    span = _first_balanced_object(text)
    return span if span is not None else text


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding markdown code fence, if present."""
    if not text.startswith(_FENCE):
        return text

    # Drop the opening fence and its optional language tag (```json).
    without_open = text[len(_FENCE):]
    newline = without_open.find("\n")
    if newline == -1:
        return text
    body = without_open[newline + 1:]

    closing = body.rfind(_FENCE)
    if closing == -1:
        return body.strip()
    return body[:closing].strip()


def _first_balanced_object(text: str) -> Optional[str]:
    """
    Return the first balanced ``{...}`` span in *text*, or None.

    Tracks string literals and backslash escapes so that braces appearing
    inside JSON string values are not counted.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None
