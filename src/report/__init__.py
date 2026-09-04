"""
Reporter package.

Produces a deterministic record of one tailoring run: ``report.json``,
``report.md`` and ``changes.md``. It consumes the structured results the
pipeline already produced and nothing else -- no LLM, no provider, no
subprocess, no Markdown parsing, no diffing, and no judgement of its own about
whether a change was correct.

The reconciliation in :mod:`src.report.reconcile` is the one derivation here,
and it exists because a ``ResumePlan`` records *intent*: the Generator cancels
some of it and the Revision Engine removes more content afterwards, so a report
that read the plan at face value would state removals that never happened.
"""

from .exceptions import IncompleteRunError, ReportError, ReportWriteError
from .gate import INITIAL_ATTEMPT_LABEL, attempt_from, gate_attempts
from .markdown import render_changes, render_report
from .models import (
    CHANGE_SECTION_ORDER,
    SECTION_LABELS,
    CheckOutcome,
    CheckStatus,
    EffectiveAction,
    EntityChange,
    FinalVerdict,
    GateAttempt,
    PlanEntry,
    Report,
    ResumeIdentity,
    ResumeShape,
    RevisionSummary,
)
from .reconcile import entity_changes, plan_entries
from .reporter import (
    CHANGES_FILENAME,
    REPORT_FILENAME,
    REPORT_JSON_FILENAME,
    Reporter,
    final_verdict,
    resume_identity,
    resume_shape,
)

__all__ = [
    # Orchestrator
    "Reporter",
    # Artifact names
    "REPORT_FILENAME",
    "CHANGES_FILENAME",
    "REPORT_JSON_FILENAME",
    # Models
    "Report",
    "ResumeIdentity",
    "ResumeShape",
    "PlanEntry",
    "EntityChange",
    "EffectiveAction",
    "CheckOutcome",
    "CheckStatus",
    "GateAttempt",
    "RevisionSummary",
    "FinalVerdict",
    "CHANGE_SECTION_ORDER",
    "SECTION_LABELS",
    # Building blocks
    "plan_entries",
    "entity_changes",
    "gate_attempts",
    "attempt_from",
    "INITIAL_ATTEMPT_LABEL",
    "render_report",
    "render_changes",
    "resume_identity",
    "resume_shape",
    "final_verdict",
    # Exceptions
    "ReportError",
    "IncompleteRunError",
    "ReportWriteError",
]
