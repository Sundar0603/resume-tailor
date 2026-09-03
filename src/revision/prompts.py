"""
The compression prompt. Prompt construction only — no calls, no parsing.

The Revision Engine is deterministic apart from this one step. The model is
given a closed list of bullets and asked to shorten each to one rendered line;
it is never asked what to delete, what matters, or what to prioritise. Those are
the application's decisions and they are already made by the time this prompt
is built.

Everything the model must not touch is absent from the prompt rather than
forbidden in it. It never sees the summary, education or contact, so it cannot
rewrite them, and the only ids it is given are the selected bullets' — an id it
invents is rejected by :mod:`src.revision.compression` on the way back in.

Every builder is a pure function of its inputs: the same candidates always
produce byte-identical prompt text.
"""

import json
from typing import Any, List, Sequence

from .measure import ONE_LINE_WORD_BUDGET
from .models import CompressionCandidate

_PROMPT_TEMPLATE = """\
You are a resume compression assistant. You shorten bullets that have already been \
chosen for you.

Your task: rewrite each bullet below so it fits on one line, and return the result \
keyed by the bullet id it came from.

Rules:
- Rewrite only the bullets listed. Return exactly one entry for each bullet id given.
- Each rewritten bullet must be {max_words} words or fewer.
- Every protected fact listed with a bullet must appear in your rewrite, unchanged. \
Copy it across character for character.
- Never invent a number. Never raise, lower or round a number that is already there. \
A percentage, count, duration or measurement is copied, not adjusted.
- Never replace a specific name with a general word. "Redis" does not become "caching", \
"Spring Boot" does not become "a framework", "OAuth 2.0" does not become \
"authentication".
- Cut filler, never facts. Remove qualifiers, connectives and throat-clearing; keep \
what was built, what it used, and what it achieved.
- Keep the past-tense verb at the front. Each bullet stays one plain professional \
sentence.
- Do not add content. Do not merge two bullets. Do not split one bullet into two.
- No markdown, no bullet characters, no quotation marks around the sentence.

Bullets to compress:
<bullets>
{bullets}
</bullets>

Required JSON schema:
{{
    "compressions": [
        {{
            "bullet_id": "<the bullet id exactly as given above>",
            "text": "<the rewritten bullet, {max_words} words or fewer>"
        }}
    ]
}}

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""


def build_compression_prompt(
    candidates: Sequence[CompressionCandidate],
    max_words: int = ONE_LINE_WORD_BUDGET,
) -> str:
    """
    Build the single consolidated compression prompt.

    One prompt for every selected bullet, never one per bullet: the task doc
    requires a single call per compression step, for latency and for
    consistency between the rewrites.

    Parameters
    ----------
    candidates
        The bullets the application selected, in selection order.
    max_words
        The hard word limit stated to the model. Application code verifies it
        afterwards regardless — the model's own claim about its word count is
        not evidence.
    """
    return _PROMPT_TEMPLATE.format(
        max_words=max_words,
        bullets=_dumps([_candidate_projection(c) for c in candidates]),
    )


def _candidate_projection(candidate: CompressionCandidate) -> Any:
    """
    Project one candidate into the shape the prompt embeds.

    Protected facts travel as one flat list. The numeric/term split matters to
    the verifier, not to the model: to the model they are all "copy these
    across", and two lists would invite it to treat one of them as advisory.
    """
    return {
        "bullet_id": candidate.bullet.bullet_id,
        "text": candidate.bullet.text,
        "protected_facts": list(candidate.facts.numerics) + list(candidate.facts.terms),
    }


def _dumps(payload: Any) -> str:
    """Serialise a projection to stable, readable JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False)


def response_markers() -> List[str]:
    """
    Return substrings that identify this prompt in a dispatching test double.

    ``tests/pipeline/conftest.py`` routes a scripted reply by matching a marker
    from each prompt's response-schema block. Exposing them here means that
    fixture cannot silently drift out of step with the prompt.
    """
    return [
        "resume compression assistant",
        '"bullet_id": "<the bullet id exactly as given above>"',
    ]
