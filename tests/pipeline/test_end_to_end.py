"""
The whole chain, end to end, offline.

```text
Source Resume + JobAnalysis + ResumePlan + Mode
  -> Generator -> Serializer -> Renderer -> Compiler -> Quality Gate
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


def run(tmp_path, rewrite=True, mode=PlanningMode.STRICT, compiler=None):
    resume = source_resume()
    provider = ScriptedProvider(resume, rewrite=rewrite)
    pipeline = ResumePipeline(provider, compiler=compiler)
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
