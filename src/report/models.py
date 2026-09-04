"""
Models the Reporter builds and renders.

Pydantic v2 with ``extra="forbid"`` and ``validate_assignment=True``, matching
every other model package in ``src/``.

Two conventions here are deliberate and worth reading before extending them.

**Nothing derived is stored where the original will do.** ``JobAnalysis`` is
embedded whole rather than copied into a parallel "job summary" model: it is
already flat, already has no free-text field, and duplicating it would give the
project two representations of the same thing to keep in step. The plan is the
one exception, and for a stated reason -- see :class:`PlanEntry`.

**No wall clock, no durations, no random ids**, for the same reason
``QualityGateResult`` and ``RevisionResult`` carry none: a report has to satisfy
``first == second`` for identical inputs, and a timestamp breaks that on every
run. Paths are stored relative to the run directory, because an absolute one
varies between two runs that are otherwise identical.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.analyzer.models import JobAnalysis
from src.parser.models import EntitySource
from src.planner.models import PlanAction, PlanningMode
from src.quality.models import QualityIssueCode, QualityStage, ResumeSection
from src.revision.models import CompressionOutcome, RevisionStep
from src.validation.models import ValidationIssue

#: The sections ``changes.md`` reports, in the order it reports them. Education
#: is included and will always be empty: it has no plan, and the Revision
#: Engine never touches it. Saying so explicitly beats leaving a reader to
#: wonder whether the section was omitted or simply never considered.
CHANGE_SECTION_ORDER = (
    ResumeSection.SUMMARY,
    ResumeSection.SKILLS,
    ResumeSection.EXPERIENCE,
    ResumeSection.PROJECTS,
    ResumeSection.EDUCATION,
)

#: Human headings for the sections above. ``ResumeSection``'s own values are the
#: literal LaTeX template headings ("WORK EXPERIENCE"), which are right for
#: attributing a PDF region and shouty in a report.
SECTION_LABELS = {
    ResumeSection.SUMMARY: "Summary",
    ResumeSection.SKILLS: "Skills",
    ResumeSection.EXPERIENCE: "Experience",
    ResumeSection.PROJECTS: "Projects",
    ResumeSection.EDUCATION: "Education",
}


class EffectiveAction(str, Enum):
    """
    What actually happened to an entity, as opposed to what was planned.

    The distinction is the whole point of the Reporter's reconciliation step.
    A ``ResumePlan`` records *intent*: the Generator then cancels a ``REMOVE``
    that no ``GENERATE`` funded, cancels a lopsided skill trade, and drops a
    category it emptied. Reporting the plan at face value would state removals
    that never happened.
    """

    KEPT = "KEPT"
    REWRITTEN = "REWRITTEN"
    REMOVED = "REMOVED"
    GENERATED = "GENERATED"
    #: Planned for removal, still present. The Generator declined the trade.
    REMOVAL_CANCELLED = "REMOVAL_CANCELLED"
    #: Absent although nothing planned its removal. Should not occur; reported
    #: rather than smoothed into ``REMOVED``, because it would mean a stage
    #: dropped an entity silently.
    DROPPED_UNPLANNED = "DROPPED_UNPLANNED"
    #: Removed by the Revision Engine to fit one page, not by the plan.
    TRIMMED_FOR_PAGE_FIT = "TRIMMED_FOR_PAGE_FIT"


class CheckStatus(str, Enum):
    """
    The state of one named Quality Gate check on one attempt.

    ``NOT_REACHED`` exists because a compilation failure returns a Stage 1
    verdict with every geometry metric at zero. Rendering those as ``PASS``
    would claim a check that never ran.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_REACHED = "NOT_REACHED"


class ResumeIdentity(BaseModel):
    """Which resume this run started from."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    resume: str = Field(min_length=1)
    template: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ResumeShape(BaseModel):
    """
    Counts and lineage for one resume, never its content.

    The task doc asks for a "resume summary" and warns against serializing
    runtime-only information unnecessarily. Entity ids and ``EntitySource`` are
    runtime state, not resume content -- the Markdown serializer drops both --
    so a full resume echo does not belong in a report. The generated-entity id
    lists *are* here, because lineage is precisely what the report is for.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    summary_word_count: int = Field(ge=0)
    skill_categories: int = Field(ge=0)
    total_skills: int = Field(ge=0)
    experiences: int = Field(ge=0)
    projects: int = Field(ge=0)
    education: int = Field(ge=0)
    total_highlights: int = Field(ge=0)
    word_count: int = Field(ge=0)
    generated_projects: List[str] = Field(default_factory=list)
    generated_skill_categories: List[str] = Field(default_factory=list)


class PlanEntry(BaseModel):
    """
    One planner decision, in one shape covering all four plan models.

    This is the one place a model is projected rather than embedded, for two
    reasons. ``SectionPriority`` is an ``IntEnum`` and serialises as ``3``
    rather than ``"MEDIUM"``, so an embedded plan is unreadable in
    ``report.json``; and the plan addresses entities by runtime id only, so it
    cannot say *which* project ``proj_002`` is. ``priority`` is therefore the
    enum's name and ``label`` the entity's human name.

    Fields that do not apply to a section are ``None`` or empty: the summary
    has no id, only projects carry a ``generation_brief``, and only skill
    categories carry ``skills_to_add``.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    section: ResumeSection
    entity_id: Optional[str] = None
    label: str = Field(min_length=1)
    action: PlanAction
    priority: str = Field(min_length=1)
    reasoning: str = ""
    rewrite_strategy: Optional[str] = None
    generation_brief: Optional[str] = None
    new_category_name: Optional[str] = None
    keywords_to_include: List[str] = Field(default_factory=list)
    themes_to_emphasize: List[str] = Field(default_factory=list)
    skills_to_add: List[str] = Field(default_factory=list)
    skills_to_remove: List[str] = Field(default_factory=list)


class EntityChange(BaseModel):
    """
    What changed for one entity, reconciled across the plan and the trail.

    ``bullets_before`` and ``bullets_after`` are the source and final highlight
    lists verbatim and **unpaired**. A rewrite maps N source bullets onto M new
    ones with no correspondence between them -- the Generator rewrites a whole
    entity at once -- so pairing them would require inventing a mapping that
    does not exist. Listing both and diffing neither is the honest form.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    section: ResumeSection
    entity_id: Optional[str] = None
    label: str = Field(min_length=1)
    source: Optional[EntitySource] = None
    planned_action: Optional[PlanAction] = None
    planned_priority: Optional[str] = None
    effective_action: EffectiveAction
    #: Set when the plan and the outcome disagree, quoting the reason the
    #: Generator or Planner recorded. Never the Reporter's own inference.
    reconciliation_note: Optional[str] = None
    bullets_before: List[str] = Field(default_factory=list)
    bullets_after: List[str] = Field(default_factory=list)
    skills_before: List[str] = Field(default_factory=list)
    skills_after: List[str] = Field(default_factory=list)
    technologies_added: List[str] = Field(default_factory=list)
    technologies_removed: List[str] = Field(default_factory=list)
    domains_added: List[str] = Field(default_factory=list)
    domains_removed: List[str] = Field(default_factory=list)
    skills_added: List[str] = Field(default_factory=list)
    skills_removed: List[str] = Field(default_factory=list)
    #: One line per Revision Engine step touching this entity, taken from the
    #: trail's own ``detail`` field.
    revision_notes: List[str] = Field(default_factory=list)
    #: The Planner's and Generator's own soft-failure notes that name this
    #: entity's id. Matched on the id as a token, not by parsing the prose:
    #: a note that does not name an id attaches to nothing.
    soft_failure_notes: List[str] = Field(default_factory=list)

    def has_changes(self) -> bool:
        """Return whether this entity changed at all."""
        if self.effective_action is not EffectiveAction.KEPT:
            return True
        if self.revision_notes or self.soft_failure_notes:
            return True
        return bool(
            self.technologies_added
            or self.technologies_removed
            or self.domains_added
            or self.domains_removed
            or self.skills_added
            or self.skills_removed
            or self.bullets_before != self.bullets_after
        )


class CheckOutcome(BaseModel):
    """One named check on one attempt, read straight off the gate's verdict."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str = Field(min_length=1)
    status: CheckStatus
    code: Optional[QualityIssueCode] = None
    #: How many findings of this kind, where the gate counts them.
    count: Optional[int] = None
    detail: Optional[str] = None


class GateAttempt(BaseModel):
    """
    One trip through render -> compile -> judge.

    ``attempt`` 1 is always the pipeline's own compile; the Revision Engine's
    attempts follow. ``label`` says which is which, because the trail numbers
    revision attempts from 1 as well and two "attempt 1"s in one report would
    be unreadable.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    attempt: int = Field(ge=1)
    label: str = Field(min_length=1)
    stage_reached: QualityStage
    page_count: int = Field(ge=0)
    spill: int = Field(ge=0)
    passed: bool
    checks: List[CheckOutcome] = Field(default_factory=list)

    @property
    def blocking(self) -> List[CheckOutcome]:
        """Return the checks that failed and therefore blocked submission."""
        return [c for c in self.checks if c.status is CheckStatus.FAIL]

    @property
    def cautions(self) -> List[CheckOutcome]:
        """Return the non-blocking findings."""
        return [c for c in self.checks if c.status is CheckStatus.WARNING]


class RevisionSummary(BaseModel):
    """
    What the Revision Engine did.

    The trail and the compression outcomes are embedded as the engine's own
    models. ``RevisionResult`` itself is not, because it carries a whole
    ``Resume`` and a whole ``QualityGateResult`` that the report already
    describes elsewhere.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    revised: bool
    attempts: int = Field(ge=0)
    deterministic_steps: int = Field(ge=0)
    compression_passes: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    trail: List[RevisionStep] = Field(default_factory=list)
    compression_outcomes: List[CompressionOutcome] = Field(default_factory=list)
    #: Relative to the run directory, so two identical runs into different
    #: directories still produce identical reports.
    pdf_path: Optional[str] = None
    tex_path: Optional[str] = None
    trail_path: Optional[str] = None


class FinalVerdict(BaseModel):
    """The delivered resume's standing, taken from the final gate result."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    passed: bool
    page_count: int = Field(ge=0)
    stage_reached: QualityStage
    total_text_lines: int = Field(ge=0)
    spill: int = Field(ge=0)
    blocking_failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Report(BaseModel):
    """
    Everything one tailoring run did, structured before it is rendered.

    Built once by :class:`~src.report.reporter.Reporter` and rendered to
    ``report.json``, ``report.md`` and ``changes.md`` without any of the three
    re-deriving anything.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: PlanningMode
    resume_identity: ResumeIdentity
    target_role: str = ""
    job_analysis: JobAnalysis
    plan_entries: List[PlanEntry] = Field(default_factory=list)
    generated_shape: ResumeShape
    final_shape: ResumeShape
    gate_attempts: List[GateAttempt] = Field(default_factory=list)
    final_verdict: FinalVerdict
    changes: List[EntityChange] = Field(default_factory=list)
    revision: Optional[RevisionSummary] = None
    planner_discarded: List[str] = Field(default_factory=list)
    generator_discarded: List[str] = Field(default_factory=list)
    generator_warnings: List[ValidationIssue] = Field(default_factory=list)

    def changed_entities(self) -> List[EntityChange]:
        """Return only the entities that actually changed."""
        return [c for c in self.changes if c.has_changes()]

    def changes_in(self, section: ResumeSection) -> List[EntityChange]:
        """Return the changed entities in one section, in report order."""
        return [c for c in self.changed_entities() if c.section is section]
