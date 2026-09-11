"""
Turning Quality Gate verdicts into a readable attempt history.

Pure functions. Every status here is *read* off a ``QualityGateResult`` -- from
the issues it raised and the metrics it measured -- and none is re-decided. In
particular ``passed`` is copied verbatim rather than recomputed from the checks
below, so the report can never disagree with the gate about the outcome.

Two subtleties the naive version gets wrong:

**Severity comes from the issue, not from the check name.** ``ORPHAN_WORD`` is
the gate's only WARNING, and it is a measured decision documented in
``PROJECT_KNOWLEDGE`` §10f. Reading each issue's own ``severity`` means the
Reporter needs no special case and cannot drift if that mapping ever changes.

**A check that never ran is not a check that passed.** A compilation failure
returns a Stage 1 verdict with every geometry metric at zero, so overlap,
rule collisions and orphans read as "0 findings" when in truth no PDF was ever
opened. Those render ``NOT_REACHED``.
"""

from typing import List, Optional, Tuple

from src.quality.models import (
    QualityGateResult,
    QualityIssueCode,
    QualitySeverity,
    QualityStage,
)
from src.revision.models import RevisionResult

from .models import CheckOutcome, CheckStatus, GateAttempt

#: Stage 1 checks: name, code, and the metric field carrying the count.
_STAGE_1_CHECKS = (
    ("Compile", QualityIssueCode.COMPILATION_FAILED, None),
    ("Page count", QualityIssueCode.INVALID_PAGE_COUNT, "page_count"),
    ("Overfull boxes", QualityIssueCode.OVERFULL_HBOX, "overfull_hbox_count"),
    ("Missing glyphs", QualityIssueCode.MISSING_GLYPH, "missing_glyph_count"),
)

#: Stage 2 checks, which need rendered geometry and so can be unreachable.
_STAGE_2_CHECKS = (
    ("Layout overlap", QualityIssueCode.TEXT_OVERLAP, "overlap_count"),
    ("Rule/text collision", QualityIssueCode.RULE_TEXT_COLLISION, "rule_collision_count"),
    ("Orphan words", QualityIssueCode.ORPHAN_WORD, "orphan_word_count"),
    (
        "Bullet spacing",
        QualityIssueCode.BULLET_SPACING_ANOMALY,
        "bullet_spacing_anomaly_count",
    ),
)

#: Label for the pipeline's own compile, which happens before any revision.
INITIAL_ATTEMPT_LABEL = "initial compile"


def _status_and_detail(
    result: QualityGateResult, code: QualityIssueCode
) -> Tuple[CheckStatus, Optional[str]]:
    """
    Return one check's status, taking severity from the issues themselves.

    No findings is ``PASS``. A finding the gate marked WARNING is ``WARNING``
    and does not block; anything else is ``FAIL``.
    """
    matching = [issue for issue in result.issues if issue.code is code]
    if not matching:
        return CheckStatus.PASS, None
    status = (
        CheckStatus.WARNING
        if matching[0].severity is QualitySeverity.WARNING
        else CheckStatus.FAIL
    )
    if len(matching) == 1:
        return status, matching[0].message
    return status, "{0} findings; first: {1}".format(len(matching), matching[0].message)


def _checks_for(
    result: QualityGateResult, definitions: Tuple, reached: bool
) -> List[CheckOutcome]:
    """Build the outcomes for one stage's checks."""
    outcomes = []  # type: List[CheckOutcome]
    for name, code, metric in definitions:
        count = getattr(result.metrics, metric) if metric is not None else None
        if not reached:
            outcomes.append(
                CheckOutcome(
                    name=name,
                    status=CheckStatus.NOT_REACHED,
                    code=code,
                    detail="stage 2 was not reached",
                )
            )
            continue
        status, detail = _status_and_detail(result, code)
        outcomes.append(
            CheckOutcome(
                name=name, status=status, code=code, count=count, detail=detail
            )
        )
    return outcomes


def attempt_from(
    result: QualityGateResult, attempt: int, label: str
) -> GateAttempt:
    """Describe one render -> compile -> judge cycle."""
    reached_stage_2 = result.stage_reached is QualityStage.STAGE_2
    checks = _checks_for(result, _STAGE_1_CHECKS, True)
    checks.extend(_checks_for(result, _STAGE_2_CHECKS, reached_stage_2))
    return GateAttempt(
        attempt=attempt,
        label=label,
        stage_reached=result.stage_reached,
        page_count=result.metrics.page_count,
        spill=result.metrics.overflow_line_count,
        passed=result.passed,
        checks=checks,
    )


def gate_attempts(
    initial: QualityGateResult, revision: Optional[RevisionResult]
) -> List[GateAttempt]:
    """
    Return the full attempt history, initial compile first.

    The Revision Engine numbers its own attempts from 1, and so does the
    pipeline's compile, so the labels carry the distinction that the numbers
    alone would lose.
    """
    attempts = [attempt_from(initial, 1, INITIAL_ATTEMPT_LABEL)]
    if revision is None:
        return attempts
    for index, result in enumerate(revision.gate_results, start=1):
        attempts.append(
            attempt_from(
                result, len(attempts) + 1, "revision attempt {0}".format(index)
            )
        )
    return attempts
