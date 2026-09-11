"""
Tailor command for Resume Tailor — the whole chain, from one command.

```text
resume-tailor tailor
    -> pick a canonical resume
    -> paste the job description
    -> run
    -> a submission-ready PDF and three reports
```

Once the run starts there is **no confirmation step**. Tailoring takes a minute
or two, and a prompt in the middle of it turns an unattended command into an
attended one for no decision the user actually wants to make.

This module is a command, not an orchestrator. ``ResumePipeline`` already
chains analyze -> plan -> generate -> serialize -> render -> compile -> judge ->
revise and returns every intermediate artifact; ``Reporter`` already turns that
result into three files. What lives here is everything the chain deliberately
does not know about: which resume, which job description, where the artifacts
go, what the user sees while waiting, and what a failure reads like.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, NoReturn, Optional, Tuple

import typer

from src.cli._common import (
    DEFAULT_CONTENT_DIRECTORY,
    FAILURE_GLYPH,
    LLM_ERRORS,
    SUCCESS_GLYPH,
    build_provider,
    fail,
    load_configuration,
    print_header,
    read_job_description,
    report_llm_error,
)
from src.analyzer.provider import LLMProvider
from src.compiler.exceptions import CompilerError
from src.generator.exceptions import GeneratorError
from src.parser.metadata_parser import ParserError
from src.parser.models import Resume
from src.parser.resume_parser import ResumeParser
from src.pipeline.exceptions import FinalResumeValidationError
from src.pipeline.models import PipelineResult
from src.pipeline.pipeline import (
    STAGE_ANALYZE,
    STAGE_COMPILE,
    STAGE_GENERATE,
    STAGE_PLAN,
    STAGE_QUALITY,
    STAGE_RENDER,
    STAGE_REVISE,
    STAGE_VALIDATE,
    ResumePipeline,
)
from src.planner.exceptions import UnknownPlanningMode
from src.planner.models import PlanningMode
from src.quality.exceptions import QualityGateError
from src.quality.models import QualityGateResult
from src.renderer.exceptions import RendererError
from src.report.exceptions import ReportError
from src.report.reporter import Reporter
from src.revision.exceptions import OnePageInfeasibleError, RevisionError

DEFAULT_RUN_ROOT = "output/runs"

#: Stage keys to the line shown while that stage runs. The pipeline announces
#: keys and holds no display state, so the wording lives here. Two of these
#: stages are the CLI's own -- parsing and reporting sit outside the pipeline,
#: and the user should not be able to tell.
STAGE_LOAD = "load"
STAGE_REPORT = "report"

_STAGE_LABELS = {
    STAGE_LOAD: "Loading source resume",
    STAGE_ANALYZE: "Analyzing job description",
    STAGE_PLAN: "Planning changes",
    STAGE_GENERATE: "Generating resume",
    STAGE_RENDER: "Rendering LaTeX",
    STAGE_COMPILE: "Compiling PDF",
    STAGE_QUALITY: "Checking layout",
    STAGE_REVISE: "Revising",
    STAGE_VALIDATE: "Validating revised resume",
    STAGE_REPORT: "Generating report",
}

_LABEL_WIDTH = max(len(label) for label in _STAGE_LABELS.values()) + 4


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


class Progress:
    """
    Prints a line per stage and ticks it when the next stage begins.

    The pipeline announces that a stage is *starting*, never that one finished,
    so the tick has to be bookkeeping on this side. That is deliberate: a run
    can end at any stage, and a pipeline that promised a completion event would
    have to decide what to emit on the way out of an exception.
    """

    def __init__(self, echo: Callable[..., None] = typer.echo) -> None:
        self._echo = echo
        self._open: Optional[str] = None

    def announce(self, stage: str) -> None:
        """Close the previous stage's line with a tick and open this one."""
        self.finish()
        label = _STAGE_LABELS.get(stage, stage)
        self._echo(f"  {(label + '...').ljust(_LABEL_WIDTH)}", nl=False)
        self._open = stage

    def finish(self) -> None:
        """Tick the open stage, if there is one. Safe to call repeatedly."""
        if self._open is not None:
            self._echo(SUCCESS_GLYPH)
            self._open = None

    def abandon(self) -> None:
        """Close the open line without a tick, because the stage failed."""
        if self._open is not None:
            self._echo("")
            self._open = None


# ---------------------------------------------------------------------------
# Canonical resume discovery
# ---------------------------------------------------------------------------


def discover_resumes(content_directory: str) -> List[Path]:
    """
    Every Markdown file in the content directory, sorted by name.

    The project supports an arbitrary number of canonical resumes, so nothing
    here knows how many there are or what they are called.
    """
    directory = Path(content_directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.md"))


def select_resume(content_directory: str) -> Path:
    """
    Choose a canonical resume, prompting only when there is a choice to make.

    One resume is not a decision, so it is not a question.
    """
    candidates = discover_resumes(content_directory)

    if not candidates:
        fail(
            f"No canonical resume found in '{content_directory}'.",
            "",
            "Add a Markdown resume to that directory, or pass --resume <path>.",
        )

    if len(candidates) == 1:
        return candidates[0]

    typer.echo("Canonical resumes:")
    typer.echo("")
    for index, path in enumerate(candidates, start=1):
        typer.echo(f"  {index}. {path.stem}")
    typer.echo("")

    choice = typer.prompt("Select a resume", type=int, default=1)
    if not 1 <= choice <= len(candidates):
        fail(f"'{choice}' is not one of the {len(candidates)} resumes listed.")
    return candidates[choice - 1]


def _explicit_resume(resume: str) -> Path:
    """
    Check a ``--resume`` path before announcing it.

    Without this the command ticks "Source resume: nope.md" and only then finds
    there is no such file, which reads as though the load succeeded.
    """
    path = Path(resume)
    if not path.is_file():
        fail(f"Resume file not found: {resume}")
    return path


def run_directory(resume_path: Path, mode: PlanningMode) -> Path:
    """
    A fresh directory per run, named for the resume, the mode and the clock.

    Runs must not overwrite one another, and a name carrying only resume and
    mode does exactly that -- a re-run leaves the previous run's report sitting
    beside the new one's PDF with nothing to say it is stale. The timestamp
    never reaches the report, so determinism is unaffected.
    """
    stem = resume_path.stem.replace("_resume", "")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(DEFAULT_RUN_ROOT) / f"{stem}_{mode.value.lower()}_{stamp}"


# ---------------------------------------------------------------------------
# Result reporting
# ---------------------------------------------------------------------------


def _print_failing_checks(quality: Optional[QualityGateResult]) -> None:
    """List the blocking findings, so a failure says what is wrong."""
    if quality is None:
        return
    typer.echo("")
    typer.echo("Blocking findings:")
    for issue in quality.errors:
        typer.echo(f"  - {issue.code.value}: {issue.message}")


def _print_artifacts(pdf_path: Optional[str], reports: Dict[str, str]) -> None:
    """Print where the deliverables landed."""
    if pdf_path:
        typer.echo("")
        typer.echo("Final resume:")
        typer.echo(f"  {pdf_path}")

    if reports:
        typer.echo("")
        typer.echo("Reports:")
        for path in reports.values():
            typer.echo(f"  {path}")


def _fail_for_stage(exc: BaseException) -> NoReturn:
    """
    Name the stage that failed, then exit non-zero.

    Ordered most-derived first, like ``_common``'s provider table and for the
    same reason. Anything unrecognised is re-raised rather than mislabelled: a
    stack trace beats a confident wrong diagnosis.

    Underlying messages are echoed rather than swallowed. Several of these
    exceptions are the only place a log path or a trail path exists, and losing
    them makes the failure undebuggable.
    """
    if isinstance(exc, OnePageInfeasibleError):
        typer.echo(f"{FAILURE_GLYPH} Could not fit the resume onto one page.")
        typer.echo(f"  {exc}")
        typer.echo("")
        typer.echo(f"  Lines still overflowing: {exc.spill}")
        typer.echo(f"  Changes applied:         {exc.steps_taken}")
        if exc.pdf_path:
            typer.echo(f"  Last PDF:                {exc.pdf_path}")
        if exc.trail_path:
            typer.echo(f"  Revision trail:          {exc.trail_path}")
        typer.echo("")
        typer.echo("No report was written: the run did not produce a final resume.")
        raise typer.Exit(code=1)

    if isinstance(exc, RevisionError):
        fail(f"Revision failed: {exc}")

    if isinstance(exc, FinalResumeValidationError):
        fail(f"The revised resume failed validation: {exc}")

    if isinstance(exc, GeneratorError):
        fail(f"Failed to generate the tailored resume: {exc}")

    if isinstance(exc, RendererError):
        fail(f"LaTeX rendering failed: {exc}")

    if isinstance(exc, CompilerError):
        log_path = getattr(exc, "log_path", None)
        if log_path:
            fail(f"PDF compilation failed: {exc}", f"  Log: {log_path}")
        fail(f"PDF compilation failed: {exc}")

    if isinstance(exc, QualityGateError):
        fail(f"Quality analysis failed: {exc}")

    if isinstance(exc, ReportError):
        # Covers both halves: IncompleteRunError from build, ReportWriteError
        # from write. "Failed to write" would misdescribe the first.
        fail(f"Failed to produce the report: {exc}")

    if isinstance(exc, LLM_ERRORS) and report_llm_error(exc):
        raise typer.Exit(code=1)

    raise exc


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def tailor(
    resume: Optional[str] = typer.Option(
        None,
        "--resume",
        help="Path to a canonical resume. Omit to choose from the content directory.",
    ),
    jd: Optional[str] = typer.Option(
        None,
        "--jd",
        help="Path to a job description file. Omit to paste one instead.",
    ),
    mode: str = typer.Option(
        "aggressive",
        "--mode",
        help="Tailoring mode: aggressive or strict.",
    ),
    content_dir: str = typer.Option(
        DEFAULT_CONTENT_DIRECTORY,
        "--content-dir",
        help="Directory holding the canonical resumes.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Override the run's artifact directory.",
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        help="Override the default configuration file path.",
        hidden=True,
    ),
) -> None:
    """
    Tailor a canonical resume to a job description, end to end.
    """
    print_header("Resume Tailor")

    try:
        resolved_mode = PlanningMode.parse(mode)
    except UnknownPlanningMode as exc:
        fail(str(exc))

    config = load_configuration(config_path)

    resume_path = _explicit_resume(resume) if resume else select_resume(content_dir)
    typer.echo(f"{SUCCESS_GLYPH} Source resume: {resume_path.name}")
    typer.echo("")

    job_description = read_job_description(jd)

    provider = build_provider(config)

    destination = Path(output) if output else run_directory(resume_path, resolved_mode)

    result, reports = _execute(
        resume_path=resume_path,
        job_description=job_description,
        mode=resolved_mode,
        destination=destination,
        provider=provider,
    )
    _print_outcome(result, reports)


def _execute(
    *,
    resume_path: Path,
    job_description: str,
    mode: PlanningMode,
    destination: Path,
    provider: LLMProvider,
) -> Tuple[PipelineResult, Dict[str, str]]:
    """
    Run the chain and write the reports, naming whatever stage fails.

    Every failure funnels through one place so no path can exit with a
    half-drawn progress line or an unlabelled traceback.
    """
    progress = Progress()

    try:
        progress.announce(STAGE_LOAD)
        source_resume = _parse_resume(resume_path, progress)

        result = ResumePipeline(provider).run(
            source_resume=source_resume,
            job_description=job_description,
            mode=mode,
            output_directory=str(destination),
            on_stage=progress.announce,
        )

        progress.announce(STAGE_REPORT)
        reporter = Reporter()
        reports = reporter.write(reporter.build(result), str(destination))
        progress.finish()
    except typer.Exit:
        raise
    except BaseException as exc:
        progress.abandon()
        _fail_for_stage(exc)

    return result, reports


def _print_outcome(result: PipelineResult, reports: Dict[str, str]) -> None:
    """
    Say what happened and where the deliverables are.

    A run that did not clear the gate still gets its report -- that is when it
    is most worth having -- but never the word "Done." and never a zero exit.
    """
    typer.echo("")

    if not result.passed:
        _print_failing_checks(result.quality)
        _print_artifacts(result.final_pdf_path, reports)
        fail("The resume did not pass the quality gate.")

    pages = result.quality.metrics.page_count if result.quality else "?"
    typer.echo(f"{SUCCESS_GLYPH} Quality gate passed — {pages} page(s).")
    _print_artifacts(result.final_pdf_path, reports)
    typer.echo("")
    typer.echo("Done.")


def _parse_resume(resume_path: Path, progress: Progress) -> Resume:
    """Parse the canonical resume, naming the stage if it fails."""
    try:
        return ResumeParser().parse(str(resume_path))
    except ParserError as exc:
        progress.abandon()
        fail(f"Failed to parse source resume: {exc}")
    except FileNotFoundError as exc:
        # ResumeParser already phrases this as "Resume file not found: <path>".
        progress.abandon()
        fail(str(exc))
