"""
QualityGate — decides whether a compiled resume is submission-ready.

It evaluates and stops. It never modifies the Resume, the LaTeX, the PDF, the
log or the templates, never removes content, never squeezes layout, and never
calls an LLM. Shortening belongs to the Revision Engine; the gate's job is to
describe the problem well enough for that component to act.

**Both stages always run.** The task doc suggests short-circuiting after Stage
1, and ``docs/ARCHITECTURE.md`` originally had Stage 2 run only *when* Stage 1
failed. Neither is right here: geometry analysis costs milliseconds, and
stopping early means the Revision Engine learns about overlap only after
spending an attempt on page count. ``stage_reached`` records how far the
evaluation got, which is ``STAGE_1`` only when compilation itself failed and
there is no PDF to analyse.

**Page count is a compression measure, so it is never the sole signal.** §10d
records a document whose bullets printed on top of each other and whose page
count therefore *improved*, from two pages to one. A one-page PDF with
colliding text fails here.
"""

from typing import Callable, List, Optional

from src.compiler.exceptions import CompilationFailedError
from src.compiler.models import CompilationResult

from .checks import find_orphans, find_overlaps, find_rule_collisions, measure_overflow
from .exceptions import QualityAnalysisError
from .geometry import PageGeometry, pdfminer_extractor
from .log_analysis import analyse_log, read_log
from .models import (
    SEVERITY_BY_CODE,
    QualityGateResult,
    QualityIssue,
    QualityIssueCode,
    QualityMetrics,
    QualitySeverity,
    QualityStage,
)

Extractor = Callable[[str], List[PageGeometry]]

EXPECTED_PAGE_COUNT = 1

# LaTeX only reports an overfull box once it exceeds \hfuzz, so the default
# reports everything the engine saw. The magnitude travels on the issue, which
# is what lets a later component tell a hairline from a real intrusion without
# changing this one.
DEFAULT_OVERFULL_TOLERANCE_POINTS = 0.0


class QualityGate:
    """Evaluates compiled artifacts and returns a structured verdict."""

    def __init__(
        self,
        extractor: Optional[Extractor] = None,
        overfull_tolerance_points: float = DEFAULT_OVERFULL_TOLERANCE_POINTS,
    ) -> None:
        """
        Build a gate.

        Parameters
        ----------
        extractor : callable, optional
            ``extractor(pdf_path) -> List[PageGeometry]``. Defaults to the
            pdfminer implementation. The seam exists so the Stage 2 rules can
            be tested against hand-built geometry with no PDF and no pdfminer,
            mirroring the Compiler's ``runner``.
        overfull_tolerance_points : float
            Overfull boxes at or below this width are not reported.
        """
        self._extractor = extractor if extractor is not None else pdfminer_extractor
        self._overfull_tolerance = overfull_tolerance_points

    def evaluate(
        self,
        pdf_path: str,
        latex_path: str,
        compiler_result: CompilationResult,
    ) -> QualityGateResult:
        """
        Judge a successful compilation.

        ``latex_path`` is accepted because the task doc names it as an input and
        the Revision Engine reports against it; the gate reads only the PDF and
        the log, because a quality judgement about the rendered document must
        be made on the rendered document.
        """
        log = analyse_log(read_log(compiler_result.log_path))
        pages = self._extractor(pdf_path)

        page_count = self._reconcile_page_count(len(pages), log.page_count)
        issues: List[QualityIssue] = []
        issues.extend(self._stage_one(page_count, log))

        overlaps = find_overlaps(pages)
        orphans = find_orphans(pages)
        collisions = find_rule_collisions(pages)
        overflow_lines, overflow_height, overflowing, per_section = measure_overflow(
            pages
        )
        issues.extend(self._stage_two(overlaps, orphans, collisions))

        metrics = QualityMetrics(
            page_count=page_count,
            overfull_hbox_count=len(self._reportable_overfull(log.overfull_points)),
            max_overfull_points=max(log.overfull_points) if log.overfull_points else 0.0,
            missing_glyph_count=len(log.missing_glyphs),
            overlap_count=len(overlaps),
            orphan_word_count=len(orphans),
            rule_collision_count=len(collisions),
            total_text_lines=sum(len(page.lines) for page in pages),
            overflow_line_count=overflow_lines,
            overflow_height_points=overflow_height,
            overflowing_sections=overflowing,
            lines_per_section=per_section,
        )
        return self._result(issues, metrics, QualityStage.STAGE_2)

    def evaluate_compilation_failure(
        self, error: CompilationFailedError
    ) -> QualityGateResult:
        """
        Judge a compilation that did not produce a usable PDF.

        The Compiler raises rather than returning a status flag, and
        ``CompilationResult`` has no ``success`` field, so this is the only way
        the ``COMPILATION_FAILED`` verdict can ever be reached. No PDF is
        opened: there is nothing to open.
        """
        log = analyse_log(read_log(error.log_path)) if error.log_path else None
        overfull = list(log.overfull_points) if log else []
        glyphs = list(log.missing_glyphs) if log else []

        issues = [
            QualityIssue(
                code=QualityIssueCode.COMPILATION_FAILED,
                severity=SEVERITY_BY_CODE[QualityIssueCode.COMPILATION_FAILED],
                stage=QualityStage.STAGE_1,
                message="Compilation failed (exit code {0}). See {1}".format(
                    error.exit_code, error.log_path
                ),
                magnitude=None,
            )
        ]
        issues.extend(self._overfull_issues(overfull))
        issues.extend(self._glyph_issues(glyphs))

        metrics = QualityMetrics(
            page_count=log.page_count if log and log.page_count else 0,
            overfull_hbox_count=len(self._reportable_overfull(overfull)),
            max_overfull_points=max(overfull) if overfull else 0.0,
            missing_glyph_count=len(glyphs),
            overlap_count=0,
            orphan_word_count=0,
            rule_collision_count=0,
            total_text_lines=0,
            overflow_line_count=0,
            overflow_height_points=0.0,
        )
        return self._result(issues, metrics, QualityStage.STAGE_1)

    # -- internals ---------------------------------------------------------

    def _reconcile_page_count(self, from_pdf: int, from_log: Optional[int]) -> int:
        """
        The PDF is the truth; the log is the cross-check.

        The PDF is the artifact being judged, and its page count is present even
        when the engine wrote no "Output written on" line. A disagreement means
        one of the two inputs does not describe the other, so it raises rather
        than quietly choosing.
        """
        if from_log is not None and from_log != from_pdf:
            raise QualityAnalysisError(
                "The PDF has {0} page(s) but the log reports {1}. The artifacts "
                "do not describe the same compilation.".format(from_pdf, from_log)
            )
        return from_pdf

    def _reportable_overfull(self, points: List[float]) -> List[float]:
        """Overfull boxes wide enough to report."""
        return [p for p in points if p > self._overfull_tolerance]

    def _stage_one(self, page_count: int, log) -> List[QualityIssue]:
        """Cheap, deterministic checks from the compiler log and page count."""
        issues: List[QualityIssue] = []
        if page_count != EXPECTED_PAGE_COUNT:
            issues.append(
                QualityIssue(
                    code=QualityIssueCode.INVALID_PAGE_COUNT,
                    severity=SEVERITY_BY_CODE[QualityIssueCode.INVALID_PAGE_COUNT],
                    stage=QualityStage.STAGE_1,
                    message="Expected exactly 1 page, found {0}.".format(page_count),
                    magnitude=float(page_count),
                )
            )
        issues.extend(self._overfull_issues(log.overfull_points))
        issues.extend(self._glyph_issues(log.missing_glyphs))
        return issues

    def _overfull_issues(self, points: List[float]) -> List[QualityIssue]:
        """One issue per reportable overfull hbox, carrying its width."""
        return [
            QualityIssue(
                code=QualityIssueCode.OVERFULL_HBOX,
                severity=SEVERITY_BY_CODE[QualityIssueCode.OVERFULL_HBOX],
                stage=QualityStage.STAGE_1,
                message="Overfull hbox, {0}pt too wide.".format(width),
                magnitude=width,
            )
            for width in sorted(self._reportable_overfull(points), reverse=True)
        ]

    def _glyph_issues(self, glyphs: List[str]) -> List[QualityIssue]:
        """
        One issue per missing glyph.

        A glyph the font lacks is dropped silently in the PDF, so the log
        warning is the only evidence that content was lost.
        """
        return [
            QualityIssue(
                code=QualityIssueCode.MISSING_GLYPH,
                severity=SEVERITY_BY_CODE[QualityIssueCode.MISSING_GLYPH],
                stage=QualityStage.STAGE_1,
                message="Missing glyph: {0}".format(glyph),
                line_text=glyph,
            )
            for glyph in sorted(glyphs)
        ]

    def _stage_two(self, overlaps, orphans, collisions) -> List[QualityIssue]:
        """Findings that need rendered geometry."""
        issues: List[QualityIssue] = []
        for upper, lower, ink in overlaps:
            issues.append(
                QualityIssue(
                    code=QualityIssueCode.TEXT_OVERLAP,
                    severity=SEVERITY_BY_CODE[QualityIssueCode.TEXT_OVERLAP],
                    stage=QualityStage.STAGE_2,
                    message="Text overlaps by {0:.2f}pt on page {1}.".format(
                        ink, upper.page
                    ),
                    page=upper.page,
                    line_text="{0} / {1}".format(
                        upper.text.strip()[:60], lower.text.strip()[:60]
                    ),
                    magnitude=ink,
                )
            )
        for line in orphans:
            issues.append(
                QualityIssue(
                    code=QualityIssueCode.ORPHAN_WORD,
                    severity=SEVERITY_BY_CODE[QualityIssueCode.ORPHAN_WORD],
                    stage=QualityStage.STAGE_2,
                    message="Orphan word on page {0}: {1!r}".format(
                        line.page, line.text.strip()
                    ),
                    page=line.page,
                    line_text=line.text.strip(),
                )
            )
        for rule, line in collisions:
            issues.append(
                QualityIssue(
                    code=QualityIssueCode.RULE_TEXT_COLLISION,
                    severity=SEVERITY_BY_CODE[QualityIssueCode.RULE_TEXT_COLLISION],
                    stage=QualityStage.STAGE_2,
                    message="A section rule is drawn through text on page "
                    "{0}.".format(line.page),
                    page=line.page,
                    line_text=line.text.strip()[:60],
                )
            )
        return issues

    def _result(
        self,
        issues: List[QualityIssue],
        metrics: QualityMetrics,
        stage: QualityStage,
    ) -> QualityGateResult:
        """Sort issues into a stable order and assemble the verdict."""
        ordered = sorted(
            issues,
            key=lambda issue: (
                issue.severity.value,
                issue.stage.value,
                issue.code.value,
                issue.page if issue.page is not None else 0,
                -(issue.magnitude if issue.magnitude is not None else 0.0),
                issue.line_text or "",
                issue.message,
            ),
        )
        blocking = [i for i in ordered if i.severity is QualitySeverity.ERROR]
        return QualityGateResult(
            passed=len(blocking) == 0,
            stage_reached=stage,
            issues=ordered,
            metrics=metrics,
        )
