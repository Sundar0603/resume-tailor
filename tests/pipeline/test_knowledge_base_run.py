"""
The full chain, driven from a Knowledge Base.

``test_end_to_end.py`` covers the single-resume path. This covers the path task
020 introduced, and the seam it adds: whether what retrieval assembles is
actually accepted by the Planner, the Generator and the Validator.

Offline throughout. The LLM is ``ScriptedProvider``; compilation is skipped
where no TeX distribution is present, exactly as the neighbouring module does.
"""

import hashlib
from pathlib import Path

import pytest

from src.analyzer.models import JobAnalysis
from src.knowledge import KnowledgeBaseParser
from src.parser.models import EntitySource
from src.pipeline import PipelineStageError, ResumePipeline
from src.pipeline.pipeline import (
    STAGE_ANALYZE,
    STAGE_GENERATE,
    STAGE_PLAN,
    STAGE_RETRIEVE,
)
from src.planner.models import PlanningMode
from src.retrieval import KnowledgeBaseRetriever, build_source_resume

from .conftest import ScriptedProvider, job_analysis_payload

KNOWLEDGE_BASE = "knowledge/knowledge_base.md"
JOB_DESCRIPTION = "Backend engineer building Java and Spring Boot services."


def load_knowledge_base():
    return KnowledgeBaseParser().parse(KNOWLEDGE_BASE)


def expected_source_resume(knowledge_base):
    """
    Reproduce what the pipeline will assemble.

    Retrieval is deterministic, so a test can build the same resume the run
    will and script the provider against its ids. That is only possible because
    there is no model in this stage.
    """
    analysis = JobAnalysis(**job_analysis_payload())
    retrieval = KnowledgeBaseRetriever().retrieve(knowledge_base, analysis)
    return build_source_resume(knowledge_base, retrieval)


def run(tmp_path, mode=PlanningMode.AGGRESSIVE, on_stage=None, revise=False):
    knowledge_base = load_knowledge_base()
    provider = ScriptedProvider(expected_source_resume(knowledge_base))
    pipeline = ResumePipeline(provider, revise=revise)
    result = pipeline.run(
        knowledge_base=knowledge_base,
        job_description=JOB_DESCRIPTION,
        mode=mode,
        output_directory=str(tmp_path),
        on_stage=on_stage,
    )
    return result, provider


class TestTheChainAcceptsWhatRetrievalAssembles:
    def test_a_run_completes(self, tmp_path):
        result, _ = run(tmp_path)
        assert result.generated_resume is not None

    def test_the_source_resume_is_the_assembled_one(self, tmp_path):
        result, _ = run(tmp_path)
        expected = expected_source_resume(load_knowledge_base())
        assert result.source_resume == expected

    def test_the_result_carries_the_knowledge_base(self, tmp_path):
        result, _ = run(tmp_path)
        assert result.knowledge_base is not None

    def test_the_result_carries_the_retrieval(self, tmp_path):
        result, _ = run(tmp_path)
        assert result.retrieval is not None
        assert result.retrieval.selected_ids("project")

    def test_markdown_is_still_written(self, tmp_path):
        run(tmp_path)
        assert (tmp_path / "generated.md").is_file()


class TestTheRetrieveStageIsAnnounced:
    def test_it_fires(self, tmp_path):
        seen = []
        run(tmp_path, on_stage=seen.append)
        assert STAGE_RETRIEVE in seen

    def test_it_sits_between_analyze_and_plan(self, tmp_path):
        seen = []
        run(tmp_path, on_stage=seen.append)
        assert seen.index(STAGE_ANALYZE) < seen.index(STAGE_RETRIEVE)
        assert seen.index(STAGE_RETRIEVE) < seen.index(STAGE_PLAN)

    def test_a_single_resume_run_never_announces_it(self, tmp_path):
        """A stage that did not run must not be reported as if it had."""
        knowledge_base = load_knowledge_base()
        source = expected_source_resume(knowledge_base)
        seen = []
        ResumePipeline(ScriptedProvider(source), revise=False).run(
            source_resume=source,
            job_description=JOB_DESCRIPTION,
            output_directory=str(tmp_path),
            on_stage=seen.append,
        )
        assert STAGE_RETRIEVE not in seen
        assert STAGE_GENERATE in seen


class TestExactlyOneSourceIsRequired:
    def test_both_raises(self, tmp_path):
        knowledge_base = load_knowledge_base()
        source = expected_source_resume(knowledge_base)
        with pytest.raises(PipelineStageError):
            ResumePipeline(ScriptedProvider(source)).run(
                source_resume=source,
                knowledge_base=knowledge_base,
                job_description=JOB_DESCRIPTION,
                output_directory=str(tmp_path),
            )

    def test_neither_raises(self, tmp_path):
        knowledge_base = load_knowledge_base()
        source = expected_source_resume(knowledge_base)
        with pytest.raises(PipelineStageError):
            ResumePipeline(ScriptedProvider(source)).run(
                job_description=JOB_DESCRIPTION,
                output_directory=str(tmp_path),
            )


class TestGeneratedDataNeverEntersTheKnowledgeBase:
    """
    Task 020 §6, the hard architectural boundary, checked rather than asserted.

    Two independent things are verified: the file on disk is untouched, and the
    in-memory Knowledge Base never acquires a GENERATED entity.
    """

    def test_the_file_is_byte_identical_after_a_run(self, tmp_path):
        before = hashlib.sha256(Path(KNOWLEDGE_BASE).read_bytes()).hexdigest()
        run(tmp_path)
        after = hashlib.sha256(Path(KNOWLEDGE_BASE).read_bytes()).hexdigest()
        assert before == after

    def test_the_in_memory_knowledge_base_is_unchanged(self, tmp_path):
        knowledge_base = load_knowledge_base()
        before = knowledge_base.model_dump_json()
        provider = ScriptedProvider(expected_source_resume(knowledge_base))
        ResumePipeline(provider, revise=False).run(
            knowledge_base=knowledge_base,
            job_description=JOB_DESCRIPTION,
            output_directory=str(tmp_path),
        )
        assert knowledge_base.model_dump_json() == before

    def test_no_knowledge_base_entity_is_ever_generated(self, tmp_path):
        result, _ = run(tmp_path)
        entities = (
            list(result.knowledge_base.skills)
            + list(result.knowledge_base.experiences)
            + list(result.knowledge_base.projects)
            + list(result.knowledge_base.education)
        )
        for entity in entities:
            assert entity.source is EntitySource.CANONICAL

    def test_a_generated_entity_is_not_in_the_knowledge_base(self, tmp_path):
        """
        The direction that actually matters: whatever the Generator invented
        must be absent from the canonical data.
        """
        result, _ = run(tmp_path)
        generated_ids = {
            project.id
            for project in result.generated_resume.projects
            if project.source is EntitySource.GENERATED
        }
        canonical_ids = {project.id for project in result.knowledge_base.projects}
        assert generated_ids & canonical_ids == set()


class TestStrictModeSeesTheWholeKnowledgeBase:
    def test_a_strict_run_completes(self, tmp_path):
        """
        Strict previously measured invention against one role-specific resume.
        It now measures against every canonical fact, so a run drawing on
        content from several of them does not trip ``enforce_strict``.
        """
        result, _ = run(tmp_path, mode=PlanningMode.STRICT)
        assert result.generated_resume is not None

    def test_strict_generates_nothing(self, tmp_path):
        result, _ = run(tmp_path, mode=PlanningMode.STRICT)
        generated = [
            entity
            for entity in list(result.generated_resume.projects)
            + list(result.generated_resume.skills)
            if entity.source is EntitySource.GENERATED
        ]
        assert generated == []
