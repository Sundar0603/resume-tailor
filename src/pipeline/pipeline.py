r"""
ResumePipeline — the whole chain, from a job description to a judged PDF.

```text
Source Resume + JobAnalysis + ResumePlan + Mode
      -> Resume Generator   -> Resume Object
      -> Markdown Serializer -> generated.md      (side branch, see below)
      -> LaTeX Renderer      -> resume.tex
      -> PDF Compiler        -> resume.pdf
      -> Quality Gate        -> QualityGateResult
      -> Revision Engine     -> one page            (only when the gate failed)
```

Every stage already exists and is tested on its own. This module only connects
them, holds no logic of its own, and keeps every intermediate artifact so a bad
resume can be traced to the stage that produced it.

**The Markdown Serializer branches; it is not a link.** An earlier version of
this chain drew it *between* the Resume Object and the LaTeX Renderer. It cannot
sit there. ``LatexRenderer.render`` takes a ``Resume``, not Markdown, so putting
the serializer in the data path means ``serialize -> parse`` -- and that
round trip is lossy by construction:

- ``source=GENERATED`` has no Markdown representation and re-parses as
  ``CANONICAL``;
- ids are renumbered positionally on parse, so a generated ``proj_007``
  comes back as ``proj_001``.

Measured, not assumed: a resume carrying one GENERATED project at ``proj_007``
returns as two CANONICAL projects at ``proj_001``/``proj_002``. That lineage is
exactly what the Revision Engine needs to know what it may touch -- an invented
project may be dropped, a canonical one may not -- so the serializer runs as a
**side branch** producing ``generated.md`` as an artifact, and the Renderer is
fed the Resume object directly.

The pipeline does not wrap stage exceptions. A ``PlannerError`` reaching the
caller unchanged is more useful than a generic failure, and each stage's
exception tree is already documented. The one exception it *handles* rather than
propagates is ``CompilationFailedError``, because the Quality Gate has a verdict
for that case and the run should end with a judgement rather than a traceback.
"""

from pathlib import Path
from typing import Callable, Optional, Tuple

from src.analyzer.analyzer import JDAnalyzer
from src.analyzer.provider import LLMProvider
from src.compiler.exceptions import CompilationFailedError
from src.compiler.models import CompilationResult
from src.compiler.pdf_compiler import PDFCompiler
from src.generator.generator import ResumeGenerator
from src.parser.models import Resume
from src.parser.resume_parser import ResumeParser
from src.planner.models import PlanningMode
from src.planner.planner import ResumePlanner
from src.quality.models import QualityGateResult
from src.quality.quality_gate import QualityGate
from src.renderer.latex_renderer import LatexRenderer
from src.renderer.markdown_serializer import MarkdownSerializer
from src.revision.models import RevisionResult
from src.revision.revision_engine import RevisionEngine
from src.validation.validator import ResumeValidator

from .exceptions import FinalResumeValidationError
from .models import PipelineResult

DEFAULT_OUTPUT_DIRECTORY = "output/runs"
DEFAULT_JOB_NAME = "resume"
MARKDOWN_FILENAME = "generated.md"

# Stage keys handed to ``run``'s optional ``on_stage`` callback, announced
# *before* each stage begins. The pipeline never prints and never tracks
# completion -- a caller that wants a tick per finished stage closes the
# previous line when the next announcement arrives. Keys, not sentences, so
# the wording belongs to whoever is displaying them.
STAGE_ANALYZE = "analyze"
STAGE_PLAN = "plan"
STAGE_GENERATE = "generate"
STAGE_RENDER = "render"
STAGE_COMPILE = "compile"
STAGE_QUALITY = "quality"
STAGE_REVISE = "revise"
STAGE_VALIDATE = "validate"


class ResumePipeline:
    """Runs every stage in order and returns everything each one produced."""

    def __init__(
        self,
        provider: LLMProvider,
        template_directory: str = "templates",
        quality_gate: Optional[QualityGate] = None,
        compiler: Optional[PDFCompiler] = None,
        reviser: Optional[RevisionEngine] = None,
        validator: Optional[ResumeValidator] = None,
        revise: bool = True,
    ) -> None:
        """
        Build a pipeline.

        Parameters
        ----------
        provider : LLMProvider
            Shared by the analyzer, planner and generator. One provider, so a
            run cannot silently mix models between stages.
        template_directory : str
            Where the frozen LaTeX templates live.
        quality_gate, compiler, reviser, validator : optional
            Injected for tests, and so a caller can tune the compile timeout or
            the gate's tolerances without this module growing knobs for them.
        """
        self._parser = ResumeParser()
        self._analyzer = JDAnalyzer(provider)
        self._planner = ResumePlanner(provider)
        self._generator = ResumeGenerator(provider)
        self._serializer = MarkdownSerializer()
        self._renderer = LatexRenderer(template_directory=template_directory)
        self._compiler = compiler if compiler is not None else PDFCompiler()
        self._gate = quality_gate if quality_gate is not None else QualityGate()
        self._reviser = (
            reviser
            if reviser is not None
            else RevisionEngine(
                provider=provider,
                template_directory=template_directory,
                compiler=self._compiler,
                quality_gate=self._gate,
            )
        )
        self._validator = validator if validator is not None else ResumeValidator()
        self._revise = revise

    @staticmethod
    def _announce(stage: str, on_stage: Optional[Callable[[str], None]]) -> None:
        """Tell the caller a stage is starting. A no-op when none was given."""
        if on_stage is not None:
            on_stage(stage)

    def run(
        self,
        source_resume: Resume,
        job_description: str,
        mode: PlanningMode = PlanningMode.AGGRESSIVE,
        output_directory: str = DEFAULT_OUTPUT_DIRECTORY,
        job_name: str = DEFAULT_JOB_NAME,
        on_stage: Optional[Callable[[str], None]] = None,
    ) -> PipelineResult:
        """
        Run the full chain and return every intermediate artifact.

        Compilation failure is not raised: the Quality Gate judges it from the
        preserved log and the result carries ``compilation=None``. Every other
        stage's exceptions propagate unchanged.

        When the gate fails and a Revision Engine is wired in, the resume is
        shortened until it passes and ``result.quality`` becomes the *final*
        verdict. ``generated_resume`` keeps its pre-revision meaning,
        ``result.initial_quality`` keeps the judgement that triggered the
        revision, and ``result.final_resume`` is what was delivered.

        Revision is skipped after a compilation failure: there is no page to
        measure, and the defect is in the document rather than its length.
        A ``RevisionError`` propagates like any other stage exception.

        ``on_stage`` is called with one of the ``STAGE_*`` keys before each
        stage begins, so a CLI can report progress across a run that takes a
        minute or more. It is announcement only: the pipeline holds no display
        state and prints nothing.
        """
        self._announce(STAGE_ANALYZE, on_stage)
        job_analysis = self._analyzer.analyze(job_description)

        self._announce(STAGE_PLAN, on_stage)
        resume_plan = self._planner.plan(source_resume, job_analysis, mode)

        self._announce(STAGE_GENERATE, on_stage)
        generated = self._generator.generate(
            source_resume=source_resume,
            job_analysis=job_analysis,
            resume_plan=resume_plan,
            mode=mode,
        )

        self._announce(STAGE_RENDER, on_stage)
        markdown = self._serializer.serialize(generated)
        latex = self._renderer.render(generated)

        destination = Path(output_directory)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / MARKDOWN_FILENAME).write_text(markdown, encoding="utf-8")

        compilation, quality = self._compile_and_judge(
            latex, output_directory, job_name, on_stage
        )

        # Held before the revision block below can overwrite ``quality``.
        initial_quality = quality

        revision = self._revise_if_needed(
            source_resume=source_resume,
            generated=generated,
            quality=quality,
            compiled=compilation is not None,
            mode=mode,
            output_directory=output_directory,
            job_name=job_name,
            on_stage=on_stage,
        )
        if revision is not None:
            quality = revision.quality

        return PipelineResult(
            revision=revision,
            planner_discarded=list(self._planner.last_discarded),
            generator_discarded=list(self._generator.last_discarded),
            generator_warnings=list(self._generator.last_warnings),
            mode=mode,
            source_resume=source_resume,
            job_analysis=job_analysis,
            resume_plan=resume_plan,
            generated_resume=generated,
            markdown=markdown,
            latex=latex,
            compilation=compilation,
            quality=quality,
            initial_quality=initial_quality,
        )

    def _compile_and_judge(
        self,
        latex: str,
        output_directory: str,
        job_name: str,
        on_stage: Optional[Callable[[str], None]],
    ) -> Tuple[Optional[CompilationResult], QualityGateResult]:
        """
        Compile the LaTeX and return the gate's verdict on the result.

        Compilation failure is not raised. The Quality Gate has an entry point
        for exactly this case -- it reads the log the compiler preserved before
        raising, and opens no PDF because there is none -- so the run ends in a
        judgement rather than a traceback, with ``compilation`` left ``None``.
        """
        self._announce(STAGE_COMPILE, on_stage)
        try:
            compilation = self._compiler.compile(
                latex, output_directory=output_directory, job_name=job_name
            )
        except CompilationFailedError as failure:
            self._announce(STAGE_QUALITY, on_stage)
            return None, self._gate.evaluate_compilation_failure(failure)

        self._announce(STAGE_QUALITY, on_stage)
        return compilation, self._gate.evaluate(
            compilation.pdf_path, compilation.tex_path, compilation
        )

    def _revise_if_needed(
        self,
        *,
        source_resume: Resume,
        generated: Resume,
        quality: QualityGateResult,
        compiled: bool,
        mode: PlanningMode,
        output_directory: str,
        job_name: str,
        on_stage: Optional[Callable[[str], None]],
    ) -> Optional[RevisionResult]:
        """
        Shorten the resume to one page, when the gate says it does not fit.

        Returns ``None`` when no revision ran, which is the caller's signal to
        keep the pre-revision verdict.

        Revision is skipped after a compilation failure: there is no page to
        measure, and the defect is in the document rather than its length.
        """
        if not (self._revise and compiled and not quality.passed):
            return None

        self._announce(STAGE_REVISE, on_stage)
        revision = self._reviser.revise(
            source_resume=source_resume,
            current_resume=generated,
            quality_result=quality,
            output_directory=output_directory,
            job_name=job_name,
        )

        self._announce(STAGE_VALIDATE, on_stage)
        self._validate_revised(source_resume, revision.resume, mode)
        return revision

    def _validate_revised(
        self, source_resume: Resume, revised: Resume, mode: PlanningMode
    ) -> None:
        """
        Re-validate what the Revision Engine returned, against the source.

        The Generator already validates its own output, so an unrevised resume
        is not checked twice. Revision is the one stage that changes a resume
        afterwards -- it deletes bullets, skills and whole projects -- and it
        checks only its own floors, never the Validator.

        ``src/revision/floors.py`` sits strictly above the Validator's
        minimums, so this is a tripwire rather than an expected failure. If it
        raises, a floor stopped covering a Validator rule and that is the bug.
        """
        result = self._validator.validate(
            source_resume=source_resume,
            generated_resume=revised,
            mode=mode,
        )
        if not result.is_valid:
            detail = "; ".join(
                f"{issue.code.value}: {issue.message}" for issue in result.errors
            )
            raise FinalResumeValidationError(
                f"The revised resume failed validation: {detail}"
            )

    def run_from_file(
        self,
        resume_path: str,
        job_description_path: str,
        mode: PlanningMode = PlanningMode.AGGRESSIVE,
        output_directory: str = DEFAULT_OUTPUT_DIRECTORY,
        job_name: str = DEFAULT_JOB_NAME,
        on_stage: Optional[Callable[[str], None]] = None,
    ) -> PipelineResult:
        """Parse a Markdown resume and a job description from disk, then run."""
        return self.run(
            source_resume=self._parser.parse(resume_path),
            job_description=Path(job_description_path).read_text(encoding="utf-8"),
            mode=mode,
            output_directory=output_directory,
            job_name=job_name,
            on_stage=on_stage,
        )
