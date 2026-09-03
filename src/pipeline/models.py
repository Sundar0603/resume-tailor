"""
What a full pipeline run produced.

Pydantic v2 with ``extra="forbid"`` and ``validate_assignment=True``, matching
every other model package in ``src/``.

Every intermediate artifact is kept. The run is a chain, and when a resume comes
out wrong the question is always *which stage did it* — a result that carried
only the final PDF would make that unanswerable.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.analyzer.models import JobAnalysis
from src.compiler.models import CompilationResult
from src.parser.models import Resume
from src.planner.models import PlanningMode, ResumePlan
from src.quality.models import QualityGateResult
from src.revision.models import RevisionResult
from src.validation.models import ValidationIssue


class PipelineResult(BaseModel):
    """
    The output of every stage, in pipeline order.

    ``compilation`` and ``quality`` are optional because a run can stop early:
    a compilation failure leaves no ``CompilationResult``, though the Quality
    Gate still produces a verdict from the preserved log.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: PlanningMode
    source_resume: Resume
    job_analysis: JobAnalysis
    resume_plan: ResumePlan
    generated_resume: Resume
    markdown: str = Field(min_length=1)
    latex: str = Field(min_length=1)
    compilation: Optional[CompilationResult] = None
    quality: Optional[QualityGateResult] = None

    #: What the Revision Engine did, when one was wired in and the first
    #: judgement failed. ``None`` means no revision was attempted --
    #: either no reviser was supplied, or the resume already passed.
    revision: Optional[RevisionResult] = None

    # Soft failures. Neither stage raises for these, and both reset them on the
    # next call, so the pipeline must capture them or they are lost -- which is
    # what a first live run showed happening. They matter: the planner drops
    # removals naming an absent skill, and the generator cancels a lopsided
    # trade, drops an emptied category, or notes a summary that lost its
    # anchors. All of that is invisible in the finished resume.
    planner_discarded: List[str] = Field(default_factory=list)
    generator_discarded: List[str] = Field(default_factory=list)
    generator_warnings: List[ValidationIssue] = Field(default_factory=list)

    @property
    def final_resume(self) -> Resume:
        """
        Return the resume that was actually delivered.

        The revised one when a revision ran, otherwise the generated one.
        ``generated_resume`` deliberately keeps its pre-revision meaning: when
        a resume comes out wrong the question is always which stage did it, and
        overwriting the generator's output would make that unanswerable.
        """
        if self.revision is not None:
            return self.revision.resume
        return self.generated_resume

    @property
    def passed(self) -> bool:
        """Whether the run produced a submission-ready resume."""
        return self.quality is not None and self.quality.passed

    @property
    def pdf_path(self) -> Optional[str]:
        """The compiled PDF, when compilation succeeded."""
        return self.compilation.pdf_path if self.compilation else None
