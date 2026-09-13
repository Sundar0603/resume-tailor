"""
Knowledge Base provenance in the report.

Task 020 §24: a report must distinguish canonical Knowledge Base data, data
generated during the run, and role-specific view data. ``EntitySource`` already
marks the second. These tests cover the first, and the part nothing else in the
run records — what the Knowledge Base held and this resume did not use.
"""

import json

import pytest

from src.analyzer.models import JobAnalysis
from src.knowledge import KnowledgeBaseParser
from src.pipeline import ResumePipeline
from src.report import Reporter
from src.retrieval import KnowledgeBaseRetriever, build_source_resume

from tests.pipeline.conftest import ScriptedProvider, job_analysis_payload

KNOWLEDGE_BASE = "knowledge/knowledge_base.md"


def run(tmp_path):
    knowledge_base = KnowledgeBaseParser().parse(KNOWLEDGE_BASE)
    retrieval = KnowledgeBaseRetriever().retrieve(
        knowledge_base, JobAnalysis(**job_analysis_payload())
    )
    source = build_source_resume(knowledge_base, retrieval)
    return ResumePipeline(ScriptedProvider(source), revise=False).run(
        knowledge_base=knowledge_base,
        job_description="Backend engineer. Java, Spring Boot.",
        output_directory=str(tmp_path),
    )


@pytest.fixture
def report(tmp_path):
    return Reporter().build(run(tmp_path))


@pytest.fixture
def rendered(report):
    return Reporter().render_report(report)


class TestTheReportCarriesRetrieval:
    def test_a_knowledge_base_run_has_a_retrieval_summary(self, report):
        assert report.retrieval is not None

    def test_it_names_the_knowledge_base(self, report):
        assert report.retrieval.knowledge_base

    def test_it_names_the_summary_variant_used(self, report):
        assert report.retrieval.summary_id.startswith("sum_")

    def test_selected_and_passed_over_are_disjoint(self, report):
        selected = {e.id for e in report.retrieval.selected}
        passed_over = {e.id for e in report.retrieval.passed_over}
        assert selected & passed_over == set()

    def test_every_scored_entity_appears_somewhere(self, report, tmp_path):
        result = run(tmp_path)
        scored = (
            len(result.retrieval.summaries)
            + len(result.retrieval.experiences)
            + len(result.retrieval.projects)
            + len(result.retrieval.skill_categories)
            + len(result.retrieval.education)
        )
        summary = report.retrieval
        assert len(summary.selected) + len(summary.passed_over) == scored


class TestTheRenderedReport:
    def test_it_has_a_knowledge_base_section(self, rendered):
        assert "## Knowledge Base" in rendered

    def test_it_lists_the_entities_used(self, rendered):
        assert "Projects used" in rendered
        assert "Skill categories used" in rendered

    def test_it_lists_what_was_not_used(self, rendered):
        assert "Canonical data not used" in rendered

    def test_it_explains_a_selection_with_matched_terms(self, rendered):
        assert " on `" in rendered

    def test_it_reports_dropped_restatements(self, rendered):
        assert "Restatements dropped" in rendered

    def test_it_says_both_remain_canonical(self, rendered):
        """
        A dropped restatement must not read as a deleted fact. Both phrasings
        stay in the Knowledge Base; only one shipped on this resume.
        """
        assert "remain in the Knowledge Base" in rendered


class TestASingleResumeRunHasNoneOfThis:
    def test_the_section_is_absent(self, tmp_path):
        from src.parser import ResumeParser

        source = ResumeParser().parse("content/backend_resume.md")
        result = ResumePipeline(ScriptedProvider(source), revise=False).run(
            source_resume=source,
            job_description="Backend engineer.",
            output_directory=str(tmp_path),
        )
        rendered = Reporter().render_report(Reporter().build(result))
        assert "## Knowledge Base" not in rendered

    def test_the_retrieval_summary_is_none(self, tmp_path):
        from src.parser import ResumeParser

        source = ResumeParser().parse("content/backend_resume.md")
        result = ResumePipeline(ScriptedProvider(source), revise=False).run(
            source_resume=source,
            job_description="Backend engineer.",
            output_directory=str(tmp_path),
        )
        assert Reporter().build(result).retrieval is None


class TestDeterminism:
    def test_two_reports_render_identically(self, tmp_path):
        first = Reporter().render_report(Reporter().build(run(tmp_path / "a")))
        second = Reporter().render_report(Reporter().build(run(tmp_path / "b")))
        assert first == second

    def test_two_reports_serialise_identically(self, tmp_path):
        first = Reporter().render_json(Reporter().build(run(tmp_path / "a")))
        second = Reporter().render_json(Reporter().build(run(tmp_path / "b")))
        assert first == second

    def test_the_json_carries_retrieval(self, tmp_path):
        payload = json.loads(Reporter().render_json(Reporter().build(run(tmp_path))))
        assert payload["retrieval"] is not None
        assert payload["retrieval"]["selected"]

    def test_no_run_directory_leaks_into_the_report(self, tmp_path):
        """
        Artifact paths vary per run; the report must not carry them, or two
        runs into different directories would differ (PROJECT_KNOWLEDGE §10i).
        """
        payload = Reporter().render_json(Reporter().build(run(tmp_path / "unique_name")))
        assert "unique_name" not in payload


class TestTheReporterOnlyReads:
    def test_it_performs_no_retrieval_of_its_own(self):
        """
        §24: "Do not make Reporter responsible for retrieval or generation."
        Checked where it could be broken — in the imports.
        """
        from pathlib import Path

        for path in sorted(Path("src/report").glob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    assert "retrieval.retriever" not in stripped, path.name
                    assert "KnowledgeBaseRetriever" not in stripped, path.name

    def test_scores_are_copied_not_recomputed(self, report, tmp_path):
        result = run(tmp_path)
        by_id = {e.id: e.score for e in report.retrieval.selected}
        for entity in result.retrieval.projects:
            if entity.selected:
                assert by_id[entity.id] == entity.score
