"""
The three rendered artifacts.

``report.md`` describes the run, ``changes.md`` describes what changed in the
resume, and ``report.json`` carries the structured record. All three are
rendered from one built ``Report``, so they cannot disagree.
"""

import copy
import json

from src.parser.models import EntitySource
from src.report import (
    CHANGES_FILENAME,
    REPORT_FILENAME,
    REPORT_JSON_FILENAME,
    Reporter,
)
from src.report.exceptions import IncompleteRunError
from src.revision.models import CompressionOutcome, EntityKind, RevisionAction

import pytest

from tests.report.conftest import (
    compression_step,
    failing_result,
    generated_project,
    make_pipeline_result,
    make_plan,
    make_revision_result,
    make_source_resume,
    passing_result,
    removal_step,
)


def _rendered(result):
    """Return the three documents for one run."""
    reporter = Reporter()
    report = reporter.build(result)
    return (
        reporter.render_report(report),
        reporter.render_changes(report),
        reporter.render_json(report),
    )


class TestReportMarkdown:
    """``report.md`` is the human summary of the whole run."""

    def test_it_carries_the_run_information(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "# Tailoring report" in report_md
        assert "- Mode: **STRICT**" in report_md
        assert "Source resume: `test`" in report_md
        assert "Target role: **Backend Engineer**" in report_md

    def test_it_summarises_the_stored_job_analysis(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "## Job analysis" in report_md
        assert "Required skills: Python, AWS" in report_md
        assert "Preferred skills: Go" in report_md
        assert "Important keywords: Python, AWS, Backend" in report_md
        assert "Design and operate backend services." in report_md

    def test_it_shows_the_plan_by_section_with_priority_names(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "## Resume plan" in report_md
        assert "`exp_001` **KEEP** (priority LOW)" in report_md
        # SectionPriority is an IntEnum and serialises as an int; a report
        # showing "priority 3" would be unreadable.
        assert "priority 3" not in report_md

    def test_it_shows_the_quality_gate_progression(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "## Quality gate" in report_md
        assert "### Attempt 1 — initial compile" in report_md
        assert "- Compile: PASS" in report_md
        assert "- Missing glyphs: PASS (0)" in report_md

    def test_it_states_the_final_result(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "## Final result" in report_md
        assert "- Quality Gate: **PASSED**" in report_md
        assert "- Pages: **1**" in report_md

    def test_it_reports_soft_failures_that_the_resume_does_not_show(self):
        result = make_pipeline_result(
            planner_discarded=["dropped an absent skill removal"],
            generator_discarded=["cancelled a lopsided skills trade"],
        )
        report_md, _, _ = _rendered(result)
        assert "### Planner discarded (1)" in report_md
        assert "dropped an absent skill removal" in report_md
        assert "cancelled a lopsided skills trade" in report_md

    def test_a_run_with_no_revision_says_so(self):
        report_md, _, _ = _rendered(make_pipeline_result())
        assert "Not run: the resume was accepted on its first compile." in report_md

    def test_a_revised_run_tabulates_its_trail_and_compressions(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.experiences[0].highlights[1] = "Shortened bullet."
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
                compression_step(
                    2, ["exp_001:bullet_2"], page_count=1, spill=0, passed=True
                ),
            ],
            gate_results=[failing_result(3), passing_result()],
            compression_passes=1,
            llm_calls=1,
            compression_outcomes=[
                CompressionOutcome(
                    bullet_id="exp_002:bullet_1",
                    accepted=False,
                    rejection="dropped the number 30%",
                )
            ],
        )
        report_md, _, _ = _rendered(
            make_pipeline_result(revision=revision, initial_quality=failing_result(7))
        )
        assert "- Deterministic removals: **1**" in report_md
        assert "- Compression passes: **1** (LLM calls: 1)" in report_md
        assert "| 1 | `REMOVE_BULLET` | `proj_001` | 2 | 3 |" in report_md
        assert "### Compression outcomes" in report_md
        assert "`exp_002:bullet_1` rejected — dropped the number 30%" in report_md


class TestChangesMarkdown:
    """``changes.md`` is about the resume, not about the run."""

    def test_an_untouched_run_reports_nothing_changed(self):
        _, changes_md, _ = _rendered(make_pipeline_result())
        assert "Nothing changed in any section." in changes_md

    def test_unchanged_sections_are_omitted_but_named(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects.append(generated_project())
        _, changes_md, _ = _rendered(
            make_pipeline_result(source_resume=source, generated_resume=generated)
        )
        assert "## Projects" in changes_md
        assert "## Skills" not in changes_md
        assert "## Unchanged" in changes_md
        assert "Skills" in changes_md.split("## Unchanged")[1]

    def test_education_is_named_as_never_changing(self):
        _, changes_md, _ = _rendered(make_pipeline_result())
        assert "Education is never planned and never revised" in changes_md

    def test_a_generated_project_is_marked_as_generated(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects.append(generated_project())
        _, changes_md, _ = _rendered(
            make_pipeline_result(source_resume=source, generated_resume=generated)
        )
        assert "_(GENERATED)_" in changes_md
        assert "effective **GENERATED**" in changes_md

    def test_a_rewrite_shows_both_bullet_lists_unpaired(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects[0].highlights = ["Rebuilt the ingest path."]
        plan = make_plan(
            project_plans=[
                {
                    "project_id": "proj_001",
                    "action": "REWRITE",
                    "priority": "HIGH",
                    "rewrite_strategy": "Lead with the metric.",
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Most relevant project.",
                },
                {
                    "project_id": "proj_002",
                    "action": "KEEP",
                    "priority": "LOW",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Still useful.",
                },
            ]
        )
        _, changes_md, _ = _rendered(
            make_pipeline_result(
                source_resume=source, generated_resume=generated, resume_plan=plan
            )
        )
        assert "planned REWRITE, effective **REWRITTEN**" in changes_md
        assert "- before:" in changes_md
        assert "- after:" in changes_md
        assert "Rebuilt the ingest path." in changes_md

    def test_revision_notes_appear_under_their_entity(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.projects[0].highlights = final.projects[0].highlights[:3]
        revision = make_revision_result(
            final,
            trail=[
                removal_step(
                    1,
                    RevisionAction.REMOVE_BULLET,
                    "proj_001",
                    EntityKind.PROJECT,
                    page_count=1,
                    spill=0,
                    passed=True,
                    detail="Delivered project item 4.",
                )
            ],
            gate_results=[passing_result()],
        )
        _, changes_md, _ = _rendered(make_pipeline_result(revision=revision))
        assert "Removed a bullet during deterministic trimming" in changes_md
        assert "Delivered project item 4." in changes_md


class TestReportJson:
    """``report.json`` is the machine-readable record."""

    def test_it_is_valid_json_carrying_the_required_sections(self):
        _, _, report_json = _rendered(make_pipeline_result())
        payload = json.loads(report_json)
        for key in (
            "mode",
            "resume_identity",
            "job_analysis",
            "plan_entries",
            "generated_shape",
            "final_shape",
            "gate_attempts",
            "final_verdict",
            "changes",
            "revision",
        ):
            assert key in payload
        assert payload["mode"] == "STRICT"

    def test_it_does_not_echo_whole_resumes(self):
        # Entity ids and EntitySource are runtime state, not resume content --
        # the Markdown serializer drops both. A full resume echo does not
        # belong in a report; counts and lineage do.
        _, _, report_json = _rendered(make_pipeline_result())
        payload = json.loads(report_json)
        assert "source_resume" not in payload
        assert "generated_resume" not in payload
        assert "final_resume" not in payload
        assert "contact" not in json.dumps(payload["final_shape"])
        assert payload["final_shape"]["experiences"] == 2

    def test_priorities_are_names_not_integers(self):
        _, _, report_json = _rendered(make_pipeline_result())
        payload = json.loads(report_json)
        assert payload["plan_entries"][0]["priority"] == "MEDIUM"

    def test_revision_paths_are_relative_to_the_run_directory(self):
        source = make_source_resume()
        revision = make_revision_result(
            source, gate_results=[passing_result()], root="/somewhere/runs/backend"
        )
        _, _, report_json = _rendered(make_pipeline_result(revision=revision))
        revision_payload = json.loads(report_json)["revision"]
        assert revision_payload["pdf_path"] == "final/resume.pdf"
        assert revision_payload["trail_path"] == "revision_trail.json"
        assert "/somewhere" not in report_json


class TestWriting:
    """The caller owns the run directory; the Reporter writes into it."""

    def test_it_writes_exactly_the_three_named_artifacts(self, tmp_path):
        reporter = Reporter()
        report = reporter.build(make_pipeline_result())
        written = reporter.write(report, str(tmp_path))
        assert set(written) == {
            REPORT_FILENAME,
            CHANGES_FILENAME,
            REPORT_JSON_FILENAME,
        }
        for name in written:
            assert (tmp_path / name).is_file()
            assert (tmp_path / name).read_text(encoding="utf-8").endswith("\n")

    def test_it_creates_a_missing_run_directory(self, tmp_path):
        reporter = Reporter()
        report = reporter.build(make_pipeline_result())
        target = tmp_path / "runs" / "backend_strict"
        reporter.write(report, str(target))
        assert (target / REPORT_FILENAME).is_file()

    def test_a_run_with_no_verdict_cannot_be_reported(self):
        result = make_pipeline_result(quality=None, initial_quality=None)
        with pytest.raises(IncompleteRunError):
            Reporter().build(result)
