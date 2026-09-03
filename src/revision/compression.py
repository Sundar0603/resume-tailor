r"""
The LLM compression path: select, validate, apply.

Everything here except the one provider call is deterministic. The application
chooses the bullets, extracts the facts, checks the reply and writes the result
onto the ``Resume``. The model contributes exactly one thing: shorter wording
for bullets it was handed.

Selection order, from the task doc::

    Projects  ->  Skills  ->  Experience (Internship -> Full-Time)

with the lowest-priority eligible bullet in each entity considered first.

**Skills are skipped, deliberately.** A skill category is not prose — it renders
as one ``Category: a, b, c`` row. Compressing it would mean either deleting
skills, which is deterministic deletion and belongs in
:mod:`src.revision.deletion`, or renaming a technology, which is *by
definition* mutating a protected fact. There is no third thing for the model to
do, so skills never reach it. This is a divergence from the literal priority
list and is pinned by a test so it stays deliberate.

Only bullets that already render as two or more lines are eligible. A one-line
bullet sent for shortening spends facts and buys no rendered space.
"""

import json
from typing import Any, Dict, List, Optional, Sequence

from src.analyzer._json_extract import extract_json_object
from src.parser.models import Resume

from . import floors
from .exceptions import InvalidCompressionJSON, InvalidCompressionResponse
from .facts import build_lexicon, extract_protected_facts, verify
from .measure import (
    ONE_LINE_WORD_BUDGET,
    bullet_id,
    estimated_lines,
    is_two_line_bullet,
    word_count,
)
from .models import (
    BulletRef,
    CompressionCandidate,
    CompressionOutcome,
    EntityKind,
)


def eligible_bullets(resume: Resume) -> List[BulletRef]:
    """
    Return every bullet eligible for compression, in selection order.

    Projects first (weakest project first, weakest bullet within it first),
    then experiences — internships before full-time roles — with the same
    bottom-to-top ordering inside each. Skills are not included; see the module
    docstring.
    """
    refs = []  # type: List[BulletRef]

    for project in reversed(resume.projects):
        refs.extend(_entity_bullets(project.id, EntityKind.PROJECT, project.highlights))

    internships = [e for e in resume.experiences if floors.is_internship(e)]
    full_time = [e for e in resume.experiences if not floors.is_internship(e)]
    for experience in internships + full_time:
        refs.extend(
            _entity_bullets(experience.id, EntityKind.EXPERIENCE, experience.highlights)
        )

    return refs


def _entity_bullets(
    entity_id: str, kind: EntityKind, highlights: Sequence[str]
) -> List[BulletRef]:
    """Return one entity's eligible bullets, lowest priority first."""
    refs = []  # type: List[BulletRef]
    for index in range(len(highlights) - 1, -1, -1):
        text = highlights[index]
        if not is_two_line_bullet(text):
            continue
        refs.append(
            BulletRef(
                bullet_id=bullet_id(entity_id, index),
                entity_id=entity_id,
                entity_kind=kind,
                index=index,
                text=text,
            )
        )
    return refs


def select_candidates(resume: Resume, shortfall: int) -> List[CompressionCandidate]:
    """
    Return the bullets to compress in this pass, with their protected facts.

    Selection is deterministic and made entirely here — the model never chooses
    what to compress. Enough bullets are taken to cover ``shortfall`` on the
    estimate that each drops to a single line; because the estimate is coarse
    the result is a starting point, and a further pass runs if the recompiled
    page still overflows.

    Parameters
    ----------
    resume
        The current resume. Bullet indices are taken against it and are only
        valid until the next removal.
    shortfall
        Rendered lines still to recover. Zero or less selects nothing.
    """
    if shortfall <= 0:
        return []

    lexicon = build_lexicon(resume)
    candidates = []  # type: List[CompressionCandidate]
    recovered = 0

    for ref in eligible_bullets(resume):
        lines = estimated_lines(ref.text)
        candidates.append(
            CompressionCandidate(
                bullet=ref,
                estimated_lines=lines,
                facts=extract_protected_facts(ref.text, lexicon),
            )
        )
        recovered += lines - 1
        if recovered >= shortfall:
            break

    return candidates


def parse_response(raw: str) -> List[Dict[str, Any]]:
    """
    Return the ``compressions`` array from a model reply.

    Raises
    ------
    InvalidCompressionResponse
        The reply is empty, or carries no usable ``compressions`` array.
    InvalidCompressionJSON
        The reply is not parseable as JSON.
    """
    if not raw or not raw.strip():
        raise InvalidCompressionResponse("the provider returned an empty reply")

    try:
        payload = json.loads(extract_json_object(raw))
    except (ValueError, json.JSONDecodeError) as error:
        raise InvalidCompressionJSON(
            "the compression reply was not valid JSON: {0}".format(error)
        )

    if not isinstance(payload, dict) or "compressions" not in payload:
        raise InvalidCompressionResponse(
            "the compression reply has no 'compressions' array"
        )

    entries = payload["compressions"]
    if not isinstance(entries, list):
        raise InvalidCompressionResponse("'compressions' is not an array")

    return [e for e in entries if isinstance(e, dict)]


def evaluate_response(
    raw: str,
    candidates: Sequence[CompressionCandidate],
    max_words: int = ONE_LINE_WORD_BUDGET,
) -> List[CompressionOutcome]:
    """
    Judge a model reply against the candidates it was given.

    Returns one outcome per candidate, in selection order, so a rejection is
    recorded rather than lost. A rejected compression is not an error: the
    original bullet is kept and the engine continues.

    Every check is made here, in application code — an unknown or duplicated
    id, a word count over the limit, a lost or altered protected fact, a
    fabricated number. The model's compliance with the prompt is not evidence
    of any of them.
    """
    entries = parse_response(raw)
    by_id = {c.bullet.bullet_id: c for c in candidates}
    returned = {}  # type: Dict[str, Optional[str]]
    rejections = {}  # type: Dict[str, str]

    for entry in entries:
        identifier = entry.get("bullet_id")
        text = entry.get("text")
        if not isinstance(identifier, str) or identifier not in by_id:
            continue
        if identifier in returned or identifier in rejections:
            rejections[identifier] = "duplicate bullet id in the reply"
            returned.pop(identifier, None)
            continue
        if not isinstance(text, str) or not text.strip():
            rejections[identifier] = "empty compressed text"
            continue
        returned[identifier] = text.strip()

    outcomes = []  # type: List[CompressionOutcome]
    for candidate in candidates:
        identifier = candidate.bullet.bullet_id
        if identifier in rejections:
            outcomes.append(_rejected(identifier, rejections[identifier]))
        elif identifier not in returned:
            outcomes.append(_rejected(identifier, "no compression returned for this bullet"))
        else:
            outcomes.append(_judge(candidate, returned[identifier], max_words))
    return outcomes


def _judge(
    candidate: CompressionCandidate, text: str, max_words: int
) -> CompressionOutcome:
    """Return the outcome for one returned compression."""
    identifier = candidate.bullet.bullet_id

    words = word_count(text)
    if words > max_words:
        return _rejected(
            identifier, "compressed to {0} words, limit is {1}".format(words, max_words)
        )

    reasons = verify(candidate.facts, text)
    if reasons:
        return _rejected(identifier, "; ".join(reasons))

    return CompressionOutcome(bullet_id=identifier, accepted=True, text=text)


def _rejected(identifier: str, reason: str) -> CompressionOutcome:
    """Return a rejection outcome."""
    return CompressionOutcome(bullet_id=identifier, accepted=False, rejection=reason)


def apply_compressions(
    resume: Resume,
    candidates: Sequence[CompressionCandidate],
    outcomes: Sequence[CompressionOutcome],
) -> Resume:
    """
    Return a new resume with every accepted compression written in.

    Only the selected bullets change. Entity ids, ``EntitySource`` values,
    bullet positions and every immutable field survive untouched, because
    nothing but one string in one list is assigned.

    The bullet's current text is re-checked against the text that was sent for
    compression. A mismatch means the resume moved under the selection and the
    compression is dropped — indices are positional and a removal renumbers
    everything after it.
    """
    accepted = {o.bullet_id: o.text for o in outcomes if o.accepted and o.text}
    if not accepted:
        return resume.model_copy(deep=True)

    revised = resume.model_copy(deep=True)
    for candidate in candidates:
        text = accepted.get(candidate.bullet.bullet_id)
        if text is None:
            continue
        owner = _owner(revised, candidate.bullet)
        if owner is None:
            continue
        index = candidate.bullet.index
        if index >= len(owner.highlights) or owner.highlights[index] != candidate.bullet.text:
            continue
        highlights = list(owner.highlights)
        highlights[index] = text
        owner.highlights = highlights

    return revised


def _owner(resume: Resume, ref: BulletRef):
    """Return the entity a bullet reference addresses, or ``None``."""
    pool = (
        resume.projects if ref.entity_kind is EntityKind.PROJECT else resume.experiences
    )
    for entity in pool:
        if entity.id == ref.entity_id:
            return entity
    return None
