"""
The whole chain, end to end, offline.

```text
Source Resume + JobAnalysis + ResumePlan + Mode
  -> Generator -> Serializer -> Renderer -> Compiler -> Quality Gate
                                                     -> Revision Engine
```

Every stage is covered in isolation elsewhere. What these tests cover is the
*seams*: whether one stage's output is actually accepted by the next. That is
the class of break that survives a thousand green unit tests, which is why this
runs on every change rather than only in a live script.

The LLM is scripted, so these need no provider and no network. Only the tests
that reach the compiler need a TeX distribution.
"""

import shutil

import pytest

from src.compiler.pdf_compiler import PDFCompiler
from src.parser import ResumeParser
from src.parser.models import EntitySource
from src.pipeline import MARKDOWN_FILENAME, ResumePipeline
from src.planner.models import PlanningMode
from src.quality.models import QualityIssueCode

from .conftest import ScriptedProvider

JOB_DESCRIPTION = "Backend engineer. Java, Spring Boot, MySQL, distributed systems."
SOURCE = "content/backend_resume.md"

needs_tex = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)


def source_resume():
    return ResumeParser().parse(SOURCE)


def run(tmp_path, rewrite=True, mode=PlanningMode.STRICT, compiler=None, revise=True):
    resume = source_resume()
    provider = ScriptedProvider(resume, rewrite=rewrite)
    pipeline = ResumePipeline(provider, compiler=compiler, revise=revise)
    result = pipeline.run(
        source_resume=resume,
        job_description=JOB_DESCRIPTION,
        mode=mode,
        output_directory=str(tmp_path),
    )
    return result, provider


class TestTheChainRuns:
    @needs_tex
    def test_every_stage_produces_its_artifact(self, tmp_path):
        result, _ = run(tmp_path)
        assert result.job_analysis.role
        assert result.resume_plan.summary_plan is not None
        assert result.generated_resume.summary
        assert result.markdown and result.latex
        assert result.compilation is not None
        assert result.quality is not None

    @needs_tex
    def test_it_reaches_a_verdict(self, tmp_path):
        result, _ = run(tmp_path)
        assert isinstance(result.passed, bool)

    @needs_tex
    def test_the_pdf_exists(self, tmp_path):
        result, _ = run(tmp_path)
        assert (tmp_path / "resume.pdf").is_file()
        assert result.pdf_path.endswith("resume.pdf")

    @needs_tex
    def test_the_generated_markdown_is_written(self, tmp_path):
        run(tmp_path)
        assert (tmp_path / MARKDOWN_FILENAME).is_file()

    @needs_tex
    def test_the_run_is_reproducible(self, tmp_path):
        # The generator is non-deterministic against a real model; against a
        # fixed provider the whole chain must be stable.
        first, _ = run(tmp_path / "a")
        second, _ = run(tmp_path / "b")
        assert first.quality.metrics == second.quality.metrics
        assert first.latex == second.latex


class TestStageWiring:
    def test_the_mode_reaches_the_plan(self, tmp_path):
        result, _ = run(tmp_path, mode=PlanningMode.STRICT, compiler=_never_compiles())
        assert result.resume_plan.mode is PlanningMode.STRICT

    def test_all_five_calls_fire_when_the_plan_rewrites(self, tmp_path):
        _, provider = run(tmp_path, rewrite=True, compiler=_never_compiles())
        assert provider.stages == [
            "analysis",
            "plan",
            "summary",
            "experiences",
            "projects",
        ]

    def test_an_all_keep_plan_makes_no_generator_call(self, tmp_path):
        # A section whose plan is entirely KEEP makes no call at all, so an
        # all-KEEP plan generates with zero calls.
        _, provider = run(tmp_path, rewrite=False, compiler=_never_compiles())
        assert provider.stages == ["analysis", "plan"]

    def test_one_provider_serves_every_stage(self, tmp_path):
        # A run must not silently mix models between stages.
        _, provider = run(tmp_path, compiler=_never_compiles())
        assert len(provider.prompts) == len(provider.stages)


class TestTheSerializerIsASideBranch:
    """
    The serializer branches off the Resume Object rather than sitting between it
    and the LaTeX Renderer. An in-path serializer would mean serialize-then-parse,
    and that round trip destroys the entity lineage the Revision Engine uses to
    decide what it may touch. These pin the reason so the chain is not re-drawn
    the old way later.
    """

    def test_the_renderer_consumes_the_resume_object(self, tmp_path):
        result, _ = run(tmp_path, compiler=_never_compiles())
        # Rendering the object directly and rendering the pipeline's LaTeX must
        # agree — proof the object, not the Markdown, fed the renderer.
        from src.renderer import LatexRenderer

        assert LatexRenderer().render(result.generated_resume) == result.latex

    def test_a_markdown_round_trip_would_lose_lineage(self, tmp_path):
        # Pinned so nobody "simplifies" the pipeline by routing through Markdown.
        result, _ = run(tmp_path, compiler=_never_compiles())
        generated = result.generated_resume
        generated.projects[0].source = EntitySource.GENERATED
        generated.projects[0].id = "proj_007"

        from src.renderer import MarkdownSerializer

        reparsed = ResumeParser().parse_string(MarkdownSerializer().serialize(generated))
        assert reparsed.projects[0].source is EntitySource.CANONICAL
        assert reparsed.projects[0].id == "proj_001"


class TestCompilationFailure:
    def test_a_failed_compile_still_returns_a_verdict(self, tmp_path):
        result, _ = run(tmp_path, compiler=_never_compiles())
        assert result.quality is not None
        assert result.compilation is None

    def test_the_verdict_names_the_compilation_failure(self, tmp_path):
        result, _ = run(tmp_path, compiler=_never_compiles())
        assert QualityIssueCode.COMPILATION_FAILED in [
            issue.code for issue in result.quality.issues
        ]

    def test_a_failed_compile_never_passes(self, tmp_path):
        result, _ = run(tmp_path, compiler=_never_compiles())
        assert result.passed is False


def _never_compiles():
    """A compiler whose engine always fails, without needing a TeX install."""

    def runner(argv, cwd, timeout, env):
        return 1, "! LaTeX Error: something went wrong.\n"

    import sys

    return PDFCompiler(engine=sys.executable, runner=runner)


class TestTheRevisionEngineIsWiredIn:
    """
    The chain now ends in a delivered resume rather than a verdict.

    These are seam tests like the rest of the file: the Revision Engine's own
    behaviour is covered in ``tests/revision/``. What matters here is that the
    Quality Gate's output is actually accepted by the engine, and that the
    engine's output reaches ``PipelineResult``.
    """

    @needs_tex
    def test_the_run_ends_on_one_page(self, tmp_path):
        result, _ = run(tmp_path)
        assert result.passed is True
        assert result.quality.metrics.page_count == 1

    @needs_tex
    def test_the_quality_verdict_is_the_final_one(self, tmp_path):
        result, _ = run(tmp_path)
        if result.revision is None:
            pytest.skip("this resume passed without revision")
        assert result.quality == result.revision.quality
        assert result.quality.passed is True

    @needs_tex
    def test_generated_resume_keeps_its_pre_revision_meaning(self, tmp_path):
        # When a resume comes out wrong the question is always which stage did
        # it. Overwriting the generator's output would make that unanswerable.
        result, _ = run(tmp_path)
        if result.revision is not None:
            assert result.final_resume is result.revision.resume
            assert result.final_resume is not result.generated_resume
        else:
            assert result.final_resume is result.generated_resume

    @needs_tex
    def test_the_revision_trail_is_written_beside_the_other_artifacts(self, tmp_path):
        result, _ = run(tmp_path)
        if result.revision is not None:
            assert (tmp_path / "revision_trail.json").is_file()
            assert (tmp_path / "final" / "resume.pdf").is_file()

    @needs_tex
    def test_revision_can_be_turned_off(self, tmp_path):
        result, _ = run(tmp_path, revise=False)
        assert result.revision is None
        assert result.final_resume is result.generated_resume

    @needs_tex
    def test_a_passing_resume_is_never_revised(self, tmp_path):
        result, _ = run(tmp_path, revise=True)
        if result.revision is None:
            assert result.passed is True

    def test_a_compilation_failure_skips_revision(self, tmp_path):
        # There is no page to measure, and the defect is in the document rather
        # than its length.
        result, _ = run(tmp_path, compiler=_never_compiles())
        assert result.compilation is None
        assert result.revision is None
        assert result.quality.issues[0].code is QualityIssueCode.COMPILATION_FAILED

    def test_the_scripted_provider_recognises_a_compression_prompt(self):
        # Guards the fixture against prompt drift: an unrecognised prompt is a
        # hard AssertionError, so this would otherwise surface as a confusing
        # failure inside an unrelated test.
        from src.revision.prompts import build_compression_prompt, response_markers
        from src.revision.models import (
            BulletRef,
            CompressionCandidate,
            EntityKind,
            ProtectedFacts,
        )

        candidate = CompressionCandidate(
            bullet=BulletRef(
                bullet_id="proj_001:bullet_1",
                entity_id="proj_001",
                entity_kind=EntityKind.PROJECT,
                index=0,
                text="Built a Redis caching layer that cut API latency by 40%.",
            ),
            estimated_lines=2,
            facts=ProtectedFacts(numerics=["40%"], terms=["Redis"]),
        )
        prompt = build_compression_prompt([candidate])
        assert all(marker in prompt for marker in response_markers())

        reply = ScriptedProvider(source_resume()).generate(prompt)
        assert "proj_001:bullet_1" in reply
        assert "40%" in reply
