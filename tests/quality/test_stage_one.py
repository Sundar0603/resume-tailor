"""
Stage 1: compilation status, page count, overfull hboxes, missing glyphs.

Note the compilation check is only reachable through
``evaluate_compilation_failure``. The Compiler raises rather than returning a
status flag, and ``CompilationResult`` has no ``success`` field, so a result
object can only ever describe a compilation that worked.
"""

import pytest

from src.compiler.exceptions import CompilationFailedError, CompilationTimeoutError
from src.quality import QualityGate, QualityIssueCode, QualityStage

from .conftest import (
    FakeExtractor,
    make_compilation_result,
    make_log,
    make_page,
    make_line,
    make_rule,
    write_log,
)


def evaluate(tmp_path, log_text, pages=None):
    """Drive the gate with a canned log and canned geometry."""
    path = write_log(tmp_path, log_text)
    geometry = pages if pages is not None else [make_page([make_line()], rules=[make_rule()])]
    gate = QualityGate(extractor=FakeExtractor(geometry))
    return gate.evaluate("resume.pdf", "resume.tex", make_compilation_result(path))


def codes(result):
    return [issue.code for issue in result.issues]


class TestCompilationFailure:
    def test_a_failure_produces_a_compilation_issue(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None))
        error = CompilationFailedError("boom", 1, path, "resume.tex")
        result = QualityGate().evaluate_compilation_failure(error)
        assert QualityIssueCode.COMPILATION_FAILED in codes(result)

    def test_a_failure_never_passes(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None))
        error = CompilationFailedError("boom", 1, path, "resume.tex")
        assert QualityGate().evaluate_compilation_failure(error).passed is False

    def test_a_failure_stops_at_stage_one(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None))
        error = CompilationFailedError("boom", 1, path, "resume.tex")
        result = QualityGate().evaluate_compilation_failure(error)
        assert result.stage_reached is QualityStage.STAGE_1

    def test_a_timeout_is_also_a_compilation_failure(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None))
        error = CompilationTimeoutError("timed out", None, path, "resume.tex")
        result = QualityGate().evaluate_compilation_failure(error)
        assert QualityIssueCode.COMPILATION_FAILED in codes(result)

    def test_it_still_reports_log_diagnostics(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None, overfull=[9.0]))
        error = CompilationFailedError("boom", 1, path, "resume.tex")
        result = QualityGate().evaluate_compilation_failure(error)
        assert QualityIssueCode.OVERFULL_HBOX in codes(result)

    def test_it_opens_no_pdf(self, tmp_path):
        # There is no PDF to open on this path.
        path = write_log(tmp_path, make_log(pages=None))
        extractor = FakeExtractor()
        error = CompilationFailedError("boom", 1, path, "resume.tex")
        QualityGate(extractor=extractor).evaluate_compilation_failure(error)
        assert extractor.calls == []


class TestSuccessfulCompilation:
    def test_a_clean_one_page_resume_passes(self, tmp_path):
        assert evaluate(tmp_path, make_log(pages=1)).passed is True

    def test_a_clean_resume_reaches_stage_two(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1))
        assert result.stage_reached is QualityStage.STAGE_2


class TestPageCount:
    def test_exactly_one_page_is_valid(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1))
        assert QualityIssueCode.INVALID_PAGE_COUNT not in codes(result)

    def test_two_pages_fail(self, tmp_path):
        pages = [
            make_page([make_line()], rules=[make_rule()]),
            make_page([make_line(page=2)], page_number=2),
        ]
        result = evaluate(tmp_path, make_log(pages=2), pages)
        assert QualityIssueCode.INVALID_PAGE_COUNT in codes(result)

    def test_more_than_two_pages_fail(self, tmp_path):
        pages = [
            make_page([make_line()], rules=[make_rule()]),
            make_page([make_line(page=2)], page_number=2),
            make_page([make_line(page=3)], page_number=3),
        ]
        result = evaluate(tmp_path, make_log(pages=3), pages)
        assert result.metrics.page_count == 3

    def test_the_observed_page_count_is_reported(self, tmp_path):
        pages = [
            make_page([make_line()], rules=[make_rule()]),
            make_page([make_line(page=2)], page_number=2),
        ]
        assert evaluate(tmp_path, make_log(pages=2), pages).metrics.page_count == 2


class TestOverfullHboxes:
    def test_none_is_clean(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1))
        assert result.metrics.overfull_hbox_count == 0

    def test_one_is_reported(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1, overfull=[12.0]))
        assert result.metrics.overfull_hbox_count == 1
        assert result.passed is False

    def test_several_are_all_reported(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1, overfull=[1.0, 2.0, 3.0]))
        assert result.metrics.overfull_hbox_count == 3

    def test_the_largest_magnitude_is_recorded(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1, overfull=[0.5, 20.0]))
        assert result.metrics.max_overfull_points == 20.0

    def test_the_tolerance_suppresses_hairlines(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=1, overfull=[0.4, 20.0]))
        gate = QualityGate(
            extractor=FakeExtractor([make_page([make_line()], rules=[make_rule()])]),
            overfull_tolerance_points=1.0,
        )
        result = gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))
        assert result.metrics.overfull_hbox_count == 1


class TestMissingGlyphs:
    def test_none_is_clean(self, tmp_path):
        assert evaluate(tmp_path, make_log(pages=1)).metrics.missing_glyph_count == 0

    def test_one_fails_the_gate(self, tmp_path):
        result = evaluate(tmp_path, make_log(pages=1, missing_glyphs=["^^c3"]))
        assert result.passed is False
        assert result.metrics.missing_glyph_count == 1

    def test_several_are_all_counted(self, tmp_path):
        result = evaluate(
            tmp_path, make_log(pages=1, missing_glyphs=["^^c3", "^^a9", "^^e2"])
        )
        assert result.metrics.missing_glyph_count == 3


class TestBothStagesAlwaysRun:
    def test_geometry_is_analysed_even_when_stage_one_fails(self, tmp_path):
        # Short-circuiting would make the Revision Engine spend an attempt on
        # page count before learning the layout is also broken.
        pages = [
            make_page([make_line()], rules=[make_rule()]),
            make_page([make_line(page=2)], page_number=2),
        ]
        extractor = FakeExtractor(pages)
        path = write_log(tmp_path, make_log(pages=2))
        gate = QualityGate(extractor=extractor)
        gate.evaluate("resume.pdf", "resume.tex", make_compilation_result(path))
        assert extractor.calls == ["resume.pdf"]
