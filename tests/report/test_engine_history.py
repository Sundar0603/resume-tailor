"""
The per-attempt gate results the Reporter's history is built from.

Task 018 added ``RevisionResult.gate_results``: the engine already computed a
full verdict on every attempt and kept only the last, so the per-check history
the report needs was being thrown away. These tests drive the **real**
``RevisionEngine`` and pin that the field agrees with the trail.

``StubCompiler`` and ``CountingGate`` come from ``tests/revision/conftest.py``:
the stub writes the renderer's genuine LaTeX and the gate measures it back, so
this needs no TeX distribution and is still a real convergence loop.
"""

from src.report import Reporter
from src.report.gate import INITIAL_ATTEMPT_LABEL
from src.revision.revision_engine import RevisionEngine

from tests.report.conftest import make_pipeline_result, make_source_resume
from tests.revision.conftest import CountingGate, ExplodingProvider, StubCompiler


def _converge(tmp_path, capacity):
    """Run a real revision against a gate that responds to trimming."""
    resume = make_source_resume(project_bullets=(5, 5), fulltime_bullets=6)
    gate = CountingGate(capacity=capacity)
    compiler = StubCompiler()
    engine = RevisionEngine(
        provider=ExplodingProvider(), quality_gate=gate, compiler=compiler
    )
    before = gate.verdict(gate.capacity + 6)
    result = engine.revise(
        source_resume=resume,
        current_resume=resume,
        quality_result=before,
        output_directory=str(tmp_path / "run"),
    )
    return resume, before, result


class TestTheEngineRecordsEveryVerdict:
    """One gate result per attempt, in order."""

    def test_there_is_one_gate_result_per_attempt(self, tmp_path):
        _, _, result = _converge(tmp_path, capacity=24)
        assert result.attempts > 0
        assert len(result.gate_results) == result.attempts

    def test_the_last_gate_result_is_the_final_verdict(self, tmp_path):
        _, _, result = _converge(tmp_path, capacity=24)
        assert result.gate_results[-1] == result.quality

    def test_the_results_agree_with_the_trail(self, tmp_path):
        _, _, result = _converge(tmp_path, capacity=24)
        for step, verdict in zip(result.trail, result.gate_results):
            assert step.page_count == verdict.metrics.page_count
            assert step.spill == verdict.metrics.overflow_line_count
            assert step.passed == verdict.passed

    def test_a_resume_that_already_passes_records_no_attempts(self, tmp_path):
        resume = make_source_resume()
        gate = CountingGate(capacity=500)
        engine = RevisionEngine(
            provider=ExplodingProvider(), quality_gate=gate, compiler=StubCompiler()
        )
        result = engine.revise(
            source_resume=resume,
            current_resume=resume,
            quality_result=gate.verdict(10),
            output_directory=str(tmp_path / "run"),
        )
        assert result.revised is False
        assert result.gate_results == []


class TestTheReportedHistory:
    """The Reporter turns those verdicts into an attempt table."""

    def test_the_history_starts_with_the_initial_compile(self, tmp_path):
        _, before, result = _converge(tmp_path, capacity=24)
        report = Reporter().build(
            make_pipeline_result(
                revision=result, initial_quality=before, quality=result.quality
            )
        )
        assert len(report.gate_attempts) == len(result.gate_results) + 1
        assert report.gate_attempts[0].label == INITIAL_ATTEMPT_LABEL
        assert report.gate_attempts[0].spill == before.metrics.overflow_line_count

    def test_the_history_ends_on_the_delivered_verdict(self, tmp_path):
        _, before, result = _converge(tmp_path, capacity=24)
        report = Reporter().build(
            make_pipeline_result(
                revision=result, initial_quality=before, quality=result.quality
            )
        )
        last = report.gate_attempts[-1]
        assert last.passed is result.quality.passed
        assert last.page_count == result.quality.metrics.page_count
        assert report.final_verdict.passed is result.quality.passed

    def test_the_spill_never_rises_across_the_history(self, tmp_path):
        # Deletion strictly shrinks the resume, so a rising spill would mean
        # the history had been assembled out of order.
        _, before, result = _converge(tmp_path, capacity=24)
        report = Reporter().build(
            make_pipeline_result(
                revision=result, initial_quality=before, quality=result.quality
            )
        )
        spills = [a.spill for a in report.gate_attempts]
        assert spills == sorted(spills, reverse=True)
