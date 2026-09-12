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

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, NoReturn, Optional, Tuple

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
from src.analyzer.models import JobAnalysis
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

#: Where the finished resume is filed, outside the repository. The run
#: directory is a working record -- every intermediate artifact, named for the
#: clock -- and nothing there is the thing you attach to an application. This
#: is: one directory per company and role, one file in it, named for what it
#: is rather than for how it was made.
DEFAULT_DELIVERY_ROOT = "/Volumes/Personal Protected/Resume Tailor/resumes"

#: The name the delivered file always takes. It is the name a recruiter sees.
DELIVERED_FILENAME = "Resume.pdf"

#: Everything else the run produced, one directory down from the resume.
#: A delivered run is self-contained: the PDF you send and the full record of
#: how it was built travel together, and ``output/runs`` accumulates only the
#: runs that failed.
ARTIFACTS_DIRNAME = "artifacts"

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
# Delivery
# ---------------------------------------------------------------------------


def _camel(text: str) -> str:
    """
    Collapse a free-text name into one path-safe word: ``Full Stack`` -> ``FullStack``.

    The job description supplies these, so they arrive with whatever
    punctuation, casing and trailing noise a hiring page had in it. A word
    that already carries a capital is left exactly as written -- the casing
    in ``iOS`` or ``AWS`` is the word, and a directory name is read by a
    human.
    """
    words = [word for word in re.split(r"[^A-Za-z0-9]+", text) if word]
    return "".join(word.capitalize() if word.islower() else word for word in words)


def delivery_folder_name(analysis: JobAnalysis) -> str:
    """
    ``Amazon-FullStackDeveloper`` -- the company and the role, nothing else.

    ``company`` is optional in a ``JobAnalysis`` because plenty of postings
    never name the employer. The role is not, so the name degrades to the role
    alone rather than to a placeholder standing where a company should be.
    """
    role = _camel(analysis.role) or "Resume"
    company = _camel(analysis.company or "")
    return f"{company}-{role}" if company else role


def delivery_directory(analysis: JobAnalysis, root: str) -> Path:
    """
    A fresh directory per delivered resume, suffixed when the name is taken.

    Two applications to the same company for the same role is a normal thing
    to do -- a revised resume, a second team -- and the second one must not
    overwrite the first. The plain name is used while it is free, so the
    common case reads exactly as specified.

    Any existing directory counts as taken, not just one holding a resume: a
    delivery that was interrupted leaves a half-filled directory behind, and
    moving a new run's artifacts into it would interleave two runs.
    """
    base = Path(root) / delivery_folder_name(analysis)
    if not base.exists():
        return base

    attempt = 2
    while (base.parent / f"{base.name}-{attempt}").exists():
        attempt += 1
    return base.parent / f"{base.name}-{attempt}"


class Delivery(NamedTuple):
    """Where a delivered run ended up. ``pdf`` is ``None`` if none was made."""

    directory: Path
    artifacts: Path
    pdf: Optional[Path]
    reports: Dict[str, str]


def _relocate(path: Optional[str], old_root: Path, new_root: Path) -> Optional[str]:
    """
    Rewrite a path inside the run directory to where it will be after a move.

    Anything outside the run directory is returned unchanged -- it is not
    moving, so a rewritten path would point at a file that never arrives.
    Computed before the move, while both ends still resolve.
    """
    if path is None:
        return None
    try:
        inside = Path(path).resolve().relative_to(old_root.resolve())
    except ValueError:
        return path
    return str(new_root / inside)


def deliver(
    result: PipelineResult,
    run_directory: Path,
    reports: Dict[str, str],
    root: str,
) -> Optional[Delivery]:
    """
    Move a finished run to its resting place, returning where things landed.

    The whole run goes: the resume to ``<Company>-<Role>/Resume.pdf`` and
    everything else to ``<Company>-<Role>/artifacts/``. A move rather than a
    copy, because two copies of a run is how a workspace fills up with
    directories nobody can tell apart -- the delivered one is the only one.

    The reports record their paths relative to the run directory, so moving
    the tree whole leaves them correct; the paths this returns are the same
    files at their new addresses.

    ``None`` means there was nothing to deliver. That is not an error here:
    the caller has already decided the run succeeded, so a delivery that
    cannot happen is reported rather than raised.
    """
    if not run_directory.is_dir():
        return None

    directory = delivery_directory(result.job_analysis, root)
    artifacts = directory / ARTIFACTS_DIRNAME

    # Worked out first: after the move the old paths no longer resolve.
    moved_pdf = _relocate(result.final_pdf_path, run_directory, artifacts)
    moved_reports = {
        name: _relocate(path, run_directory, artifacts) or path
        for name, path in reports.items()
    }

    directory.mkdir(parents=True, exist_ok=True)
    shutil.move(str(run_directory), str(artifacts))

    delivered = None  # type: Optional[Path]
    if moved_pdf is not None and Path(moved_pdf).is_file():
        delivered = directory / DELIVERED_FILENAME
        shutil.copy2(moved_pdf, delivered)

    return Delivery(
        directory=directory,
        artifacts=artifacts,
        pdf=delivered,
        reports=moved_reports,
    )


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
    deliver_to: Optional[str] = typer.Option(
        None,
        "--deliver-to",
        help=f"Directory the finished resume is filed under. Default: {DEFAULT_DELIVERY_ROOT}",
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
    _print_outcome(
        result,
        reports,
        run_directory=destination,
        delivery_root=deliver_to or DEFAULT_DELIVERY_ROOT,
    )


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


def _print_outcome(
    result: PipelineResult,
    reports: Dict[str, str],
    *,
    run_directory: Path,
    delivery_root: str,
) -> None:
    """
    Say what happened and where the deliverables are.

    A run that did not clear the gate still gets its report -- that is when it
    is most worth having -- but never the word "Done." and never a zero exit.
    It is also never delivered, and so keeps its working directory: the
    delivery directory holds resumes that are ready to send, and one that
    failed the gate is not.
    """
    typer.echo("")

    if not result.passed:
        _print_failing_checks(result.quality)
        _print_artifacts(result.final_pdf_path, reports)
        fail("The resume did not pass the quality gate.")

    pages = result.quality.metrics.page_count if result.quality else "?"
    typer.echo(f"{SUCCESS_GLYPH} Quality gate passed — {pages} page(s).")

    delivery = _deliver_or_warn(result, run_directory, reports, delivery_root)

    if delivery is None:
        _print_artifacts(result.final_pdf_path, reports)
    else:
        _print_artifacts(
            str(delivery.pdf) if delivery.pdf else None, delivery.reports
        )
        typer.echo("")
        typer.echo("Artifacts:")
        typer.echo(f"  {delivery.artifacts}")

    typer.echo("")
    typer.echo("Done.")


def _deliver_or_warn(
    result: PipelineResult,
    run_directory: Path,
    reports: Dict[str, str],
    delivery_root: str,
) -> Optional[Delivery]:
    """
    File the finished run, and say so plainly when that could not be done.

    The resume exists either way by this point, so a delivery that fails --
    an unmounted volume, a directory that cannot be written -- must not turn
    a successful run into a failed one. It downgrades to a warning, and the
    run keeps the working directory whose paths the caller then prints.
    """
    try:
        return deliver(result, run_directory, reports, delivery_root)
    except OSError as exc:
        typer.echo("")
        typer.echo(
            f"{FAILURE_GLYPH} Could not file the run under {delivery_root}: {exc}"
        )
        typer.echo(f"  Artifacts are still in {run_directory}")
        return None


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
