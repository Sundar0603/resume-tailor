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
from pathlib import Path

import pytest

from src.compiler.models import CompilationResult
from src.compiler.pdf_compiler import PDFCompiler
from src.parser import ResumeParser
from src.parser.models import EntitySource
from src.pipeline import MARKDOWN_FILENAME, ResumePipeline
from src.pipeline.exceptions import FinalResumeValidationError
from src.pipeline.pipeline import (
    STAGE_ANALYZE,
    STAGE_COMPILE,
    STAGE_GENERATE,
    STAGE_PLAN,
    STAGE_QUALITY,
    STAGE_RENDER,
    STAGE_REVISE,
    STAGE_VALIDATE,
)
from src.planner.models import PlanningMode
from src.quality.models import QualityIssueCode
from src.quality.quality_gate import QualityGate
from src.revision.models import RevisionResult
from src.revision.revision_engine import RevisionEngine
from src.validation.codes import ValidationCode
from src.validation.models import ValidationIssue, ValidationResult
from src.validation.validator import ResumeValidator

from tests.revision.conftest import failing_result, passing_result

from .conftest import ScriptedProvider

JOB_DESCRIPTION = "Backend engineer. Java, Spring Boot, MySQL, distributed systems."
SOURCE = "content/backend_resume.md"

needs_tex = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)


def source_resume():
    return ResumeParser().parse(SOURCE)


def run(
    tmp_path,
    rewrite=True,
    mode=PlanningMode.STRICT,
    compiler=None,
    revise=True,
    on_stage=None,
    validator=None,
):
    resume = source_resume()
    provider = ScriptedProvider(resume, rewrite=rewrite)
    pipeline = ResumePipeline(
        provider, compiler=compiler, revise=revise, validator=validator
    )
    result = pipeline.run(
        source_resume=resume,
        job_description=JOB_DESCRIPTION,
        mode=mode,
        output_directory=str(tmp_path),
        on_stage=on_stage,
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


class TestStageAnnouncements:
    """
    ``on_stage`` exists so a CLI can report progress across a run that takes a
    minute or more. It is announcement only: the pipeline holds no display
    state and prints nothing, so what these tests pin is *which* stages fire
    and in what order.
    """

    def _stages(self, tmp_path, **kwargs):
        seen = []
        result, _ = run(tmp_path, on_stage=seen.append, **kwargs)
        return result, seen

    @needs_tex
    def test_the_stages_arrive_in_pipeline_order(self, tmp_path):
        _, seen = self._stages(tmp_path)
        assert seen[:6] == [
            STAGE_ANALYZE,
            STAGE_PLAN,
            STAGE_GENERATE,
            STAGE_RENDER,
            STAGE_COMPILE,
            STAGE_QUALITY,
        ]

    @needs_tex
    def test_every_announced_stage_is_a_known_key(self, tmp_path):
        _, seen = self._stages(tmp_path)
        known = {
            STAGE_ANALYZE,
            STAGE_PLAN,
            STAGE_GENERATE,
            STAGE_RENDER,
            STAGE_COMPILE,
            STAGE_QUALITY,
            STAGE_REVISE,
            STAGE_VALIDATE,
        }
        assert set(seen) <= known

    @needs_tex
    def test_revision_is_announced_only_when_it_runs(self, tmp_path):
        # A passing run that still printed "Revising..." would describe work
        # nobody did.
        result, seen = self._stages(tmp_path)
        assert (STAGE_REVISE in seen) is (result.revision is not None)

    @needs_tex
    def test_validation_follows_revision_and_never_precedes_it(self, tmp_path):
        result, seen = self._stages(tmp_path)
        if result.revision is None:
            assert STAGE_VALIDATE not in seen
        else:
            assert seen.index(STAGE_VALIDATE) > seen.index(STAGE_REVISE)

    def test_a_failed_compile_announces_the_verdict_but_not_revision(self, tmp_path):
        # Offline: this is the one announcement path that needs no TeX.
        _, seen = self._stages(tmp_path, compiler=_never_compiles())
        assert STAGE_QUALITY in seen
        assert STAGE_REVISE not in seen

    def test_the_callback_is_optional(self, tmp_path):
        # Every other test in this file runs without one; this states it.
        result, _ = run(tmp_path, compiler=_never_compiles(), on_stage=None)
        assert result.quality is not None


class _RecordingValidator(ResumeValidator):
    """Records every call and can be told to report the resume invalid."""

    def __init__(self, valid=True):
        super().__init__()
        self.calls = []
        self._valid = valid

    def validate(self, *, source_resume, generated_resume, mode="STRICT"):
        self.calls.append((source_resume, generated_resume, mode))
        if self._valid:
            return super().validate(
                source_resume=source_resume,
                generated_resume=generated_resume,
                mode=mode,
            )
        return ValidationResult(
            is_valid=False,
            errors=[
                ValidationIssue(
                    code=ValidationCode.MISSING_SUMMARY,
                    message="deliberately rejected by the test",
                )
            ],
        )


class TestTheRevisedResumeIsRevalidated:
    """
    The Generator validates its own output, so an unrevised resume is not
    checked twice. Revision is the one stage that changes a resume afterwards,
    and it checks only its own floors -- never the Validator.

    ``src/revision/floors.py`` sits strictly above the Validator's minimums, so
    this should never fire on real content. It is a tripwire: if it raises, a
    floor stopped covering a Validator rule.
    """

    @needs_tex
    def test_a_revised_resume_is_validated_against_the_source(self, tmp_path):
        validator = _RecordingValidator()
        result, _ = run(tmp_path, validator=validator)
        if result.revision is None:
            pytest.skip("this resume passed without revision")
        assert len(validator.calls) == 1
        source, revised, mode = validator.calls[0]
        assert source is result.source_resume
        assert revised is result.revision.resume
        assert mode is PlanningMode.STRICT

    @needs_tex
    def test_an_unrevised_run_is_not_validated_twice(self, tmp_path):
        validator = _RecordingValidator()
        result, _ = run(tmp_path, revise=False, validator=validator)
        assert result.revision is None
        assert validator.calls == []

    def test_a_compilation_failure_is_not_validated(self, tmp_path):
        validator = _RecordingValidator()
        run(tmp_path, compiler=_never_compiles(), validator=validator)
        assert validator.calls == []

    @needs_tex
    def test_an_invalid_revised_resume_stops_the_run(self, tmp_path):
        validator = _RecordingValidator(valid=False)
        try:
            result, _ = run(tmp_path, validator=validator)
        except FinalResumeValidationError as exc:
            assert "deliberately rejected by the test" in str(exc)
            return
        if result.revision is not None:
            raise AssertionError("a rejected revised resume should have raised")
        pytest.skip("this resume passed without revision")


# ---------------------------------------------------------------------------
# A forced revision, offline
# ---------------------------------------------------------------------------
#
# The backend fixture fits on one page, so every revision-dependent test above
# skips and the revise -> validate wiring is never actually exercised. These
# stubs force the branch with no TeX and no LLM: a compiler that reports
# success, a gate that reports failure, and an engine that returns a resume.
# The engine's own behaviour is covered in ``tests/revision/``; what is under
# test here is only that the pipeline hands its output on correctly.


class _AlwaysCompiles(PDFCompiler):
    """Reports a successful compile without running an engine."""

    def compile(self, latex_source, output_directory=None, job_name="resume"):
        directory = Path(output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        tex = directory / f"{job_name}.tex"
        tex.write_text(latex_source, encoding="utf-8")
        log = directory / f"{job_name}.log"
        log.write_text("stub log\n", encoding="utf-8")
        pdf = directory / f"{job_name}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return CompilationResult(
            pdf_path=str(pdf),
            log_path=str(log),
            tex_path=str(tex),
            engine="stub",
            exit_code=0,
            duration_seconds=0.0,
        )


class _AlwaysFailsTheGate(QualityGate):
    """A gate whose verdict is always two pages."""

    def evaluate(self, pdf_path, latex_path, compiler_result):
        return failing_result()


class _StubReviser(RevisionEngine):
    """Returns a shortened resume that clears the gate, without compiling."""

    def __init__(self):
        super().__init__(provider=None)
        self.calls = []

    def revise(
        self,
        *,
        source_resume,
        current_resume,
        quality_result,
        output_directory="output/runs",
        job_name="resume",
    ):
        self.calls.append(current_resume)
        revised = current_resume.model_copy(deep=True)
        return RevisionResult(
            resume=revised,
            quality=passing_result(),
            revised=True,
            attempts=1,
            deterministic_steps=1,
            compression_passes=0,
            llm_calls=0,
        )


def forced_revision_run(tmp_path, validator=None, on_stage=None):
    """Run the chain with the revision branch guaranteed to be taken."""
    resume = source_resume()
    provider = ScriptedProvider(resume, rewrite=True)
    reviser = _StubReviser()
    pipeline = ResumePipeline(
        provider,
        compiler=_AlwaysCompiles(),
        quality_gate=_AlwaysFailsTheGate(),
        reviser=reviser,
        validator=validator,
    )
    result = pipeline.run(
        source_resume=resume,
        job_description=JOB_DESCRIPTION,
        mode=PlanningMode.STRICT,
        output_directory=str(tmp_path),
        on_stage=on_stage,
    )
    return result, reviser


class TestTheRevisionBranchIsTaken:
    def test_the_engine_receives_the_generated_resume(self, tmp_path):
        result, reviser = forced_revision_run(tmp_path)
        assert reviser.calls == [result.generated_resume]

    def test_the_final_verdict_replaces_the_initial_one(self, tmp_path):
        result, _ = forced_revision_run(tmp_path)
        assert result.initial_quality.passed is False
        assert result.quality.passed is True
        assert result.passed is True

    def test_both_stages_are_announced(self, tmp_path):
        seen = []
        forced_revision_run(tmp_path, on_stage=seen.append)
        assert seen.index(STAGE_VALIDATE) == seen.index(STAGE_REVISE) + 1

    def test_the_revised_resume_is_validated_against_the_source(self, tmp_path):
        validator = _RecordingValidator()
        result, _ = forced_revision_run(tmp_path, validator=validator)
        assert len(validator.calls) == 1
        source, revised, mode = validator.calls[0]
        assert source is result.source_resume
        assert revised is result.revision.resume
        assert mode is PlanningMode.STRICT

    def test_an_invalid_revised_resume_stops_the_run(self, tmp_path):
        validator = _RecordingValidator(valid=False)
        with pytest.raises(FinalResumeValidationError):
            forced_revision_run(tmp_path, validator=validator)

    def test_the_failure_names_the_validation_error(self, tmp_path):
        validator = _RecordingValidator(valid=False)
        try:
            forced_revision_run(tmp_path, validator=validator)
        except FinalResumeValidationError as exc:
            assert "deliberately rejected by the test" in str(exc)
        else:
            raise AssertionError("expected FinalResumeValidationError")
