"""
The Reporter is deterministic, and it mutates nothing.

Both properties are load-bearing. A report that changes between two identical
runs cannot be diffed to find out what a code change did, and a reporter that
mutated a resume would corrupt the artifact it was describing.
"""

import copy
import json

from src.revision.models import EntityKind, RevisionAction
from src.report import Reporter

from tests.report.conftest import (
    failing_result,
    generated_category,
    generated_project,
    make_pipeline_result,
    make_revision_result,
    make_source_resume,
    passing_result,
    removal_step,
)


def _rich_result(root="/runs/example"):
    """Return a run exercising generation, trimming and multiple attempts."""
    source = make_source_resume()
    generated = copy.deepcopy(source)
    generated.projects.append(generated_project())
    generated.skills.append(generated_category())
    final = copy.deepcopy(generated)
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
                spill=3,
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
        gate_results=[failing_result(3), passing_result()],
        root=root,
    )
    return make_pipeline_result(
        source_resume=source,
        generated_resume=generated,
        revision=revision,
        initial_quality=failing_result(7),
        quality=passing_result(),
    )


class TestDeterminism:
    """Identical inputs give identical output, byte for byte."""

    def test_the_same_run_builds_an_equal_report(self):
        first = Reporter().build(_rich_result())
        second = Reporter().build(_rich_result())
        assert first == second

    def test_the_three_documents_are_byte_identical_across_builds(self):
        reporter = Reporter()
        first = reporter.build(_rich_result())
        second = reporter.build(_rich_result())
        assert reporter.render_report(first) == reporter.render_report(second)
        assert reporter.render_changes(first) == reporter.render_changes(second)
        assert reporter.render_json(first) == reporter.render_json(second)

    def test_two_run_directories_produce_the_same_json(self):
        # The trap a single-directory determinism test misses entirely:
        # absolute artifact paths differ between two otherwise identical runs,
        # so they are stored relative to the run directory.
        reporter = Reporter()
        here = reporter.render_json(reporter.build(_rich_result("/runs/one")))
        there = reporter.render_json(reporter.build(_rich_result("/tmp/other/two")))
        assert here == there

    def test_the_report_carries_no_wall_clock_field(self):
        # Same reason QualityGateResult and RevisionResult carry no
        # duration_seconds: a timestamp breaks equality on every run.
        payload = json.dumps(json.loads(Reporter().render_json(_report())))
        for forbidden in ("timestamp", "generated_at", "duration", "elapsed"):
            assert forbidden not in payload.lower()

    def test_writing_twice_leaves_identical_files(self, tmp_path):
        reporter = Reporter()
        report = reporter.build(_rich_result())
        first = tmp_path / "first"
        second = tmp_path / "second"
        reporter.write(report, str(first))
        reporter.write(report, str(second))
        for name in ("report.md", "changes.md", "report.json"):
            assert (first / name).read_text(encoding="utf-8") == (
                second / name
            ).read_text(encoding="utf-8")


def _report():
    """Return a built report for the rich run."""
    return Reporter().build(_rich_result())


class TestPurity:
    """The Reporter reads its inputs and writes none of them."""

    def test_it_mutates_nothing_it_is_given(self):
        result = _rich_result()
        before = result.model_dump_json()
        reporter = Reporter()
        report = reporter.build(result)
        reporter.render_report(report)
        reporter.render_changes(report)
        reporter.render_json(report)
        assert result.model_dump_json() == before

    def test_the_trail_it_reports_is_a_copy(self):
        result = _rich_result()
        report = Reporter().build(result)
        report.revision.trail.pop()
        assert len(result.revision.trail) == 2

    def test_the_package_makes_no_llm_call(self):
        # There is no provider parameter to fake, so the invariant is checked
        # where it can actually be broken: the imports. Mirrors the "single
        # home" style of test in tests/revision/test_floors.py.
        import pathlib

        forbidden = ("provider", "providers", "sampling", "prompts", "subprocess")
        for module in pathlib.Path("src/report").glob("*.py"):
            text = module.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                for name in forbidden:
                    assert name not in stripped, "{0}: {1}".format(module.name, line)
