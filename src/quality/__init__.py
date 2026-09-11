"""
Quality Gate package.

Judges whether a compiled resume PDF is submission-ready. The Compiler answers
"did the engine produce a readable PDF"; this package answers "is the result
worth sending", which is a different and harder question — every known failure
mode compiles cleanly with exit 0.

Evaluation only. It never modifies the Resume, the LaTeX, the PDF, the log or
the templates, never removes content, never squeezes layout to force a pass,
and never calls an LLM. Shortening belongs to the Revision Engine.
"""

from .checks import (
    BULLET_GAP_MAX_POINTS,
    ORPHAN_MAX_WORDS,
    ORPHAN_PRECEDING_FILL_RATIO,
    OVERLAP_TOLERANCE_POINTS,
    attribute_sections,
    find_bullet_spacing_anomalies,
    find_orphans,
    find_overlaps,
    find_rule_collisions,
    measure_overflow,
)
from .exceptions import (
    GeometryUnavailableError,
    PDFUnreadableError,
    QualityAnalysisError,
    QualityGateError,
)
from .geometry import PageGeometry, Rule, TextLine, pdfminer_extractor
from .log_analysis import LogFindings, analyse_log, read_log
from .models import (
    REVISION_ORDER,
    SEVERITY_BY_CODE,
    QualityGateResult,
    QualityIssue,
    QualityIssueCode,
    QualityMetrics,
    QualitySeverity,
    QualityStage,
    ResumeSection,
)
from .quality_gate import EXPECTED_PAGE_COUNT, QualityGate

__all__ = [
    # Gate
    "QualityGate",
    "EXPECTED_PAGE_COUNT",
    # Results
    "QualityGateResult",
    "QualityIssue",
    "QualityIssueCode",
    "QualityMetrics",
    "QualitySeverity",
    "QualityStage",
    "ResumeSection",
    "SEVERITY_BY_CODE",
    "REVISION_ORDER",
    # Geometry
    "pdfminer_extractor",
    "PageGeometry",
    "TextLine",
    "Rule",
    # Checks
    "find_overlaps",
    "find_orphans",
    "find_bullet_spacing_anomalies",
    "find_rule_collisions",
    "attribute_sections",
    "measure_overflow",
    "OVERLAP_TOLERANCE_POINTS",
    "ORPHAN_MAX_WORDS",
    "ORPHAN_PRECEDING_FILL_RATIO",
    "BULLET_GAP_MAX_POINTS",
    # Log analysis
    "analyse_log",
    "read_log",
    "LogFindings",
    # Exceptions
    "QualityGateError",
    "GeometryUnavailableError",
    "PDFUnreadableError",
    "QualityAnalysisError",
]
