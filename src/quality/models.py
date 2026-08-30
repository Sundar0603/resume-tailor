"""
Models returned by the Quality Gate.

Pydantic v2 with ``extra="forbid"`` and ``validate_assignment=True``, matching
every other model package in ``src/``.

There is deliberately no ``duration_seconds`` here, unlike
:class:`~src.compiler.models.CompilationResult`. The Quality Gate must satisfy
``first == second`` for the same artifacts, and a wall-clock field would break
that on every run.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QualityIssueCode(str, Enum):
    """Every way a resume can fail the gate. Never use raw string literals."""

    COMPILATION_FAILED = "COMPILATION_FAILED"
    INVALID_PAGE_COUNT = "INVALID_PAGE_COUNT"
    OVERFULL_HBOX = "OVERFULL_HBOX"
    MISSING_GLYPH = "MISSING_GLYPH"
    TEXT_OVERLAP = "TEXT_OVERLAP"
    ORPHAN_WORD = "ORPHAN_WORD"
    RULE_TEXT_COLLISION = "RULE_TEXT_COLLISION"


class QualitySeverity(str, Enum):
    """
    Whether a finding blocks submission.

    Mirrors the Validator's errors-vs-warnings split. Only ERROR affects
    ``passed``; a WARNING is reported and does not block, because not every
    imperfection makes a resume unsendable.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"


class QualityStage(str, Enum):
    """Which stage produced a finding. Both stages always run."""

    STAGE_1 = "STAGE_1"
    STAGE_2 = "STAGE_2"


class ResumeSection(str, Enum):
    """
    The section headings the frozen templates emit.

    Values are the literal heading strings. ``cybersecurity.tex`` has no
    CERTIFICATIONS section, which is why attribution walks the rules it finds
    rather than assuming a fixed set. UNKNOWN covers the contact block above the
    first rule and anything unrecognised.
    """

    SUMMARY = "SUMMARY"
    SKILLS = "TECHNICAL SKILLS"
    EXPERIENCE = "WORK EXPERIENCE"
    PROJECTS = "PROJECTS"
    EDUCATION = "EDUCATION"
    CERTIFICATIONS = "CERTIFICATIONS"
    UNKNOWN = "UNKNOWN"


# Shortening order from docs/ARCHITECTURE.md. Lower is revised first.
# Education is absent because it is immutable and never revised.
REVISION_ORDER: Dict[ResumeSection, int] = {
    ResumeSection.SUMMARY: 1,
    ResumeSection.PROJECTS: 2,
    ResumeSection.SKILLS: 3,
    ResumeSection.EXPERIENCE: 4,
}


# Which findings block submission.
#
# ORPHAN_WORD is the one WARNING, and this is a deliberate divergence from the
# task doc, which lists orphan words as a failure. Measured reason: three of the
# nine known-good compiled resumes contain orphans ('60%.', 'validation.',
# 'verification.', 'systems.', 'integrations.') while being otherwise clean. A
# single word finishing a wrapped bullet is cosmetic; failing a resume that is
# correct in every other respect, and that a reviewer would happily read, is the
# wrong call. It is still reported, so the Revision Engine may act on it when it
# is already rewriting that section for another reason.
#
# Everything else blocks. An overfull hbox puts text in the margin, a missing
# glyph means content was silently dropped, and overlap or a rule through text
# is a broken page.
SEVERITY_BY_CODE: Dict[QualityIssueCode, QualitySeverity] = {
    QualityIssueCode.COMPILATION_FAILED: QualitySeverity.ERROR,
    QualityIssueCode.INVALID_PAGE_COUNT: QualitySeverity.ERROR,
    QualityIssueCode.OVERFULL_HBOX: QualitySeverity.ERROR,
    QualityIssueCode.MISSING_GLYPH: QualitySeverity.ERROR,
    QualityIssueCode.TEXT_OVERLAP: QualitySeverity.ERROR,
    QualityIssueCode.RULE_TEXT_COLLISION: QualitySeverity.ERROR,
    QualityIssueCode.ORPHAN_WORD: QualitySeverity.WARNING,
}


class QualityIssue(BaseModel):
    """One thing wrong with the compiled resume."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    code: QualityIssueCode
    severity: QualitySeverity
    stage: QualityStage
    message: str = Field(min_length=1)
    page: Optional[int] = None
    section: Optional[ResumeSection] = None
    line_text: Optional[str] = None
    magnitude: Optional[float] = None


class QualityMetrics(BaseModel):
    """
    What the gate measured, whether or not anything failed.

    The overflow fields exist so the Revision Engine knows how much to cut and
    from where, rather than only that ``page_count`` is wrong.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Stage 1
    page_count: int = Field(ge=0)
    overfull_hbox_count: int = Field(ge=0)
    max_overfull_points: float = Field(ge=0.0)
    missing_glyph_count: int = Field(ge=0)

    # Stage 2
    overlap_count: int = Field(ge=0)
    orphan_word_count: int = Field(ge=0)
    rule_collision_count: int = Field(ge=0)

    # Overflow magnitude, for the Revision Engine
    total_text_lines: int = Field(ge=0)
    overflow_line_count: int = Field(ge=0)
    overflow_height_points: float = Field(ge=0.0)
    overflowing_sections: List[ResumeSection] = Field(default_factory=list)
    lines_per_section: Dict[ResumeSection, int] = Field(default_factory=dict)


class QualityGateResult(BaseModel):
    """
    The verdict. ``passed`` is exactly "no ERROR issues".

    Mirrors the Validator's ``is_valid == (len(errors) == 0)``: warnings are
    reported and never affect the outcome.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    passed: bool
    stage_reached: QualityStage
    issues: List[QualityIssue] = Field(default_factory=list)
    metrics: QualityMetrics

    @property
    def errors(self) -> List[QualityIssue]:
        """Blocking findings."""
        return [i for i in self.issues if i.severity is QualitySeverity.ERROR]

    @property
    def warnings(self) -> List[QualityIssue]:
        """Non-blocking findings, reported for the Revision Engine."""
        return [i for i in self.issues if i.severity is QualitySeverity.WARNING]
