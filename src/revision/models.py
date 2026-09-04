"""
Models used and returned by the Revision Engine.

Pydantic v2 with ``extra="forbid"`` and ``validate_assignment=True``, matching
every other model package in ``src/``.

The action and reason vocabularies are enums rather than strings so the
persisted ``revision_trail.json`` cannot drift: the trail is the artifact that
actually gets read when a resume comes out wrong, and a typo'd reason code in
it is worse than no code at all.

There is deliberately no ``duration_seconds`` on :class:`RevisionResult`, for
the same reason the Quality Gate omits one: the deterministic phase must
satisfy ``first == second`` for the same inputs, and a wall-clock field breaks
that on every run.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.parser.models import Resume
from src.quality.models import QualityGateResult


class EntityKind(str, Enum):
    """Which kind of entity a bullet or removal belongs to."""

    PROJECT = "PROJECT"
    EXPERIENCE = "EXPERIENCE"
    SKILL_CATEGORY = "SKILL_CATEGORY"


class RevisionAction(str, Enum):
    """
    Every change the engine is allowed to make.

    Names follow ``tasks/017-revision-engine.md``'s trail examples.
    ``REMOVE_BULLET`` covers both project and experience highlights — the
    entity id says which, and a separate code per section would make the trail
    harder to scan for no gain.
    """

    REMOVE_BULLET = "REMOVE_BULLET"
    REMOVE_PROJECT = "REMOVE_PROJECT"
    REMOVE_SKILLS = "REMOVE_SKILLS"
    REMOVE_SKILL_CATEGORY = "REMOVE_SKILL_CATEGORY"
    COMPRESS_BULLETS = "COMPRESS_BULLETS"


class RevisionReason(str, Enum):
    """Why a step was taken. Never use raw string literals."""

    PAGE_OVERFLOW = "PAGE_OVERFLOW"
    PROJECT_REACHED_BULLET_FLOOR = "PROJECT_REACHED_BULLET_FLOOR"
    SKILL_CATEGORY_EMPTIED = "SKILL_CATEGORY_EMPTIED"
    SHORTFALL_REMAINS = "SHORTFALL_REMAINS"


class BulletRef(BaseModel):
    """
    A stable reference to one highlight inside one entity.

    ``bullet_id`` is ``"{entity_id}:bullet_{n}"`` with **1-based** ``n``,
    matching the task doc's ``proj_002:bullet_3``. The index is positional and
    is computed against the resume snapshot held at the moment of selection —
    removing a bullet renumbers everything after it, so a ref must never be
    carried across a deletion.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    bullet_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    entity_kind: EntityKind
    index: int = Field(ge=0)
    text: str = Field(min_length=1)


class ProtectedFacts(BaseModel):
    """
    What must survive compression of one bullet, unchanged.

    Split in two because they are verified differently. ``numerics`` are
    compared as exact strings — ``40%`` may not become ``50%`` or ``40 percent``
    — while ``terms`` are compared after normalisation, so ``Spring Boot``
    still matches across a punctuation change but not across a generalisation
    into ``framework``.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    numerics: List[str] = Field(default_factory=list)
    terms: List[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Return whether this bullet carries nothing that needs protecting."""
        return not self.numerics and not self.terms


class CompressionCandidate(BaseModel):
    """One bullet selected for compression, with everything the LLM needs."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    bullet: BulletRef
    estimated_lines: int = Field(ge=1)
    facts: ProtectedFacts


class RemovalStep(BaseModel):
    """
    One legal deterministic removal, described but not yet applied.

    Separating "decide" from "apply" is what makes the whole deletion policy
    testable without a renderer, a compiler or a PDF: ``next_removal`` is a
    pure function of the resume, and ``apply_removal`` is a pure function of
    the resume and the step.

    ``lines_freed`` is the *estimated* rendered saving. It orders and sizes the
    work; it never decides whether the resume fits. See
    :mod:`src.revision.measure`.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action: RevisionAction
    reason: RevisionReason
    entity_kind: EntityKind
    entity_id: str = Field(min_length=1)
    #: Index into the entity's own list. A bullet index for REMOVE_BULLET, the
    #: project's index for REMOVE_PROJECT, the category's for the skill actions.
    index: int = Field(ge=0)
    #: Skill strings this step removes. Empty for every non-skill action.
    skills: List[str] = Field(default_factory=list)
    detail: str = ""
    lines_freed: int = Field(ge=0)


class CompressionOutcome(BaseModel):
    """
    What happened to one candidate after the model replied.

    Rejections are recorded rather than dropped. A compression pass that
    silently kept every original bullet and a pass that was never made look
    identical in the finished resume, and the difference matters when the run
    ends in ``OnePageInfeasibleError``.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    bullet_id: str = Field(min_length=1)
    accepted: bool
    text: Optional[str] = None
    rejection: Optional[str] = None


class RevisionStep(BaseModel):
    """
    One entry in the revision trail.

    Every step is recorded, not just the checkpoints that get their own
    artifact directory. Eight intermediate PDFs nobody opens are clutter; the
    trail is what gets read.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    attempt: int = Field(ge=1)
    action: RevisionAction
    reason: RevisionReason
    entity_id: Optional[str] = None
    entity_kind: Optional[EntityKind] = None
    detail: Optional[str] = None
    bullet_ids: List[str] = Field(default_factory=list)
    shortfall_before: Optional[int] = None

    # Filled in after the step was rendered, compiled and judged.
    page_count: Optional[int] = None
    spill: Optional[int] = None
    passed: Optional[bool] = None


class RevisionResult(BaseModel):
    """
    Everything one revision produced.

    ``resume`` is the changed resume the task doc requires as the return
    value; the rest is what makes a run explicable afterwards. It is never the
    original failing resume unless the original already passed.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    resume: Resume
    quality: QualityGateResult
    revised: bool
    attempts: int = Field(ge=0)
    deterministic_steps: int = Field(ge=0)
    compression_passes: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    trail: List[RevisionStep] = Field(default_factory=list)
    compression_outcomes: List[CompressionOutcome] = Field(default_factory=list)

    #: The gate's verdict on every attempt, in order. ``trail`` carries only
    #: each step's ``page_count``/``spill``/``passed``, which is enough to see
    #: convergence but not *which check* failed; the Reporter needs the full
    #: per-attempt verdict to render a quality-gate history, and the engine
    #: already computes one every attempt. Empty when nothing was attempted.
    gate_results: List[QualityGateResult] = Field(default_factory=list)

    pdf_path: Optional[str] = None
    tex_path: Optional[str] = None
    trail_path: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Return whether the delivered resume clears the Quality Gate."""
        return self.quality.passed
