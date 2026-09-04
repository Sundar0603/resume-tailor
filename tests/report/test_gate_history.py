"""
The Quality Gate history: every attempt, and what each check actually said.

The Reporter reads verdicts; it never re-decides one. These tests pin that,
and pin the two cases where reading naively would state something false.
"""

import copy

from src.compiler.exceptions import CompilationFailedError
from src.quality.models import QualityIssueCode, QualityStage
from src.quality.quality_gate import QualityGate
from src.report import CheckStatus, Reporter
from src.report.gate import INITIAL_ATTEMPT_LABEL
from src.revision.models import EntityKind, RevisionAction

from tests.report.conftest import (
    failing_result,
    make_pipeline_result,
    make_revision_result,
    make_source_resume,
    passing_result,
    removal_step,
)


def _check(attempt, name):
    """Return one named check from an attempt."""
    matches = [c for c in attempt.checks if c.name == name]
    assert len(matches) == 1
    return matches[0]


class TestASingleAttempt:
    """A run that passed on its first compile."""

    def test_one_attempt_labelled_as_the_initial_compile(self):
        report = Reporter().build(make_pipeline_result())
        assert len(report.gate_attempts) == 1
        assert report.gate_attempts[0].label == INITIAL_ATTEMPT_LABEL
        assert report.gate_attempts[0].attempt == 1

    def test_a_passing_run_reports_one_page_and_no_blocking_checks(self):
        report = Reporter().build(make_pipeline_result())
        attempt = report.gate_attempts[0]
        assert attempt.passed is True
        assert attempt.page_count == 1
        assert attempt.blocking == []
        assert report.final_verdict.passed is True
        assert report.final_verdict.page_count == 1

    def test_an_orphan_word_is_a_warning_and_never_blocks(self):
        # ORPHAN_WORD is the gate's only WARNING, and that is a measured
        # decision (PROJECT_KNOWLEDGE 10f). Reporting it as a failure would
        # fail a resume a reviewer would happily read.
        report = Reporter().build(make_pipeline_result())
        attempt = report.gate_attempts[0]
        orphans = _check(attempt, "Orphan words")
        assert orphans.status is CheckStatus.WARNING
        assert orphans in attempt.cautions
        assert orphans not in attempt.blocking
        assert attempt.passed is True


class TestMultipleAttempts:
    """A run the Revision Engine had to shorten."""

    def _report(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.projects[0].highlights = final.projects[0].highlights[:2]
        revision = make_revision_result(
            final,
            trail=[
                removal_step(
                    1,
                    RevisionAction.REMOVE_BULLET,
                    "proj_001",
                    EntityKind.PROJECT,
                    page_count=2,
                    spill=4,
                    passed=False,
                ),
                removal_step(
                    2,
                    RevisionAction.REMOVE_BULLET,
                    "proj_001",
                    EntityKind.PROJECT,
                    page_count=1,
                    spill=0,
                    passed=True,
                ),
            ],
            gate_results=[failing_result(4), passing_result()],
        )
        return Reporter().build(
            make_pipeline_result(
                revision=revision,
                initial_quality=failing_result(13),
                quality=passing_result(),
            )
        )

    def test_every_attempt_appears_once_numbered_from_the_initial_compile(self):
        report = self._report()
        assert [a.attempt for a in report.gate_attempts] == [1, 2, 3]
        assert report.gate_attempts[0].label == INITIAL_ATTEMPT_LABEL
        assert report.gate_attempts[1].label == "revision attempt 1"
        assert report.gate_attempts[2].label == "revision attempt 2"

    def test_the_progression_shows_the_spill_closing(self):
        report = self._report()
        assert [a.spill for a in report.gate_attempts] == [13, 4, 0]
        assert [a.page_count for a in report.gate_attempts] == [2, 2, 1]
        assert [a.passed for a in report.gate_attempts] == [False, False, True]

    def test_the_pre_revision_verdict_survives_the_revision(self):
        # The pipeline overwrites ``quality`` with the final verdict, so
        # without ``initial_quality`` the judgement that triggered the
        # revision would be unrecoverable.
        report = self._report()
        assert report.gate_attempts[0].passed is False
        assert report.final_verdict.passed is True

    def test_a_failing_attempt_names_its_blocking_check(self):
        report = self._report()
        first = report.gate_attempts[0]
        blocking = [c.code for c in first.blocking]
        assert QualityIssueCode.INVALID_PAGE_COUNT in blocking


class TestAFailedRun:
    """A run that ends without a submission-ready resume."""

    def test_a_failing_gate_with_no_revision_reports_failure(self):
        report = Reporter().build(
            make_pipeline_result(
                quality=failing_result(9), initial_quality=failing_result(9)
            )
        )
        assert report.final_verdict.passed is False
        assert report.final_verdict.page_count == 2
        assert report.final_verdict.blocking_failures
        assert report.revision is None

    def test_a_compilation_failure_marks_stage_two_checks_not_reached(self, tmp_path):
        # The gate returns a Stage 1 verdict with every geometry metric at
        # zero, because no PDF was ever opened. Rendering those as PASS would
        # claim a check that never ran.
        log = tmp_path / "resume.log"
        log.write_text("! Undefined control sequence.\n", encoding="utf-8")
        failure = CompilationFailedError(
            "pdflatex exited 1",
            exit_code=1,
            log_path=str(log),
            tex_path=str(tmp_path / "resume.tex"),
        )
        verdict = QualityGate().evaluate_compilation_failure(failure)
        report = Reporter().build(
            make_pipeline_result(quality=verdict, initial_quality=verdict)
        )
        attempt = report.gate_attempts[0]
        assert attempt.stage_reached is QualityStage.STAGE_1
        assert _check(attempt, "Compile").status is CheckStatus.FAIL
        for name in ("Layout overlap", "Rule/text collision", "Orphan words"):
            assert _check(attempt, name).status is CheckStatus.NOT_REACHED
        assert report.final_verdict.passed is False
