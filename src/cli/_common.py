"""
Shared CLI plumbing.

``analyze`` and ``plan`` each carried their own copy of the provider bootstrap,
the LLM error ladder and the printer helpers. ``tailor`` would have been the
third, which is the point at which duplication stops being cheaper than an
extraction.

Nothing here makes a decision. It loads configuration, builds a provider, reads
a job description, prints, and turns a known exception into a message plus a
non-zero exit. Every rule about *what* to do with those things stays in the
command that owns it.

**The error ladder is a table, not a chain of ``except`` clauses.** Both existing
commands depend on an ordering hazard: the arms only behave because every
subclass is listed before its base. Written as clauses that constraint is
invisible and one reordering breaks it silently. As an ordered table walked with
``isinstance``, the order *is* the data, and a caller can delegate to it from a
single ``except`` without losing it.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List, NoReturn, Optional, Sequence, Tuple, Type

import typer

from src.analyzer import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
    MissingJobRole,
)
from src.analyzer.provider import LLMProvider
from src.config.credentials import CredentialManager
from src.config.exceptions import ConfigError
from src.config.manager import ConfigManager
from src.config.models import ResumeTailorConfig
from src.planner import (
    InvalidPlannerJSON,
    InvalidPlannerResponse,
    PlanConsistencyError,
    PlannerError,
    ResumePlanValidationError,
)
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.factory import ProviderFactory

#: Where canonical resumes live. A CLI default rather than a configuration key:
#: ``ResumeTailorConfig`` is provider-only, forbids extra keys, and its TOML
#: serializer is hand-rolled, so a new key would need two changes to hold a
#: value the command line can default. Mirrors ``template_directory="templates"``,
#: which is threaded the same way.
DEFAULT_CONTENT_DIRECTORY = "content"

SUCCESS_GLYPH = "✓"
FAILURE_GLYPH = "✗"
BULLET_GLYPH = "•"


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def print_header(title: str) -> None:
    """Print a command's title, surrounded by blank lines."""
    typer.echo("")
    typer.echo(title)
    typer.echo("")


def print_section(title: str) -> None:
    """Print an underlined section heading."""
    typer.echo("")
    typer.echo(title)
    typer.echo("-" * len(title))


def print_list(items: Sequence) -> None:
    """Print a bulleted list, or ``(none)`` when it is empty."""
    if not items:
        typer.echo("  (none)")
        return
    for item in items:
        typer.echo(f"  {BULLET_GLYPH} {item}")


def print_field(label: str, value: Any) -> None:
    """Print ``label: value``, skipping the line when there is no value."""
    if value is None or value == "":
        return
    typer.echo(f"  {label}: {value}")


def fail(message: str, *extra: str) -> NoReturn:
    """Echo a failure message plus any follow-up lines, then exit non-zero."""
    typer.echo(f"{FAILURE_GLYPH} {message}")
    for line in extra:
        typer.echo(line)
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Configuration and provider
# ---------------------------------------------------------------------------


def load_configuration(config_path: Optional[str]) -> ResumeTailorConfig:
    """
    Load the stored configuration, or exit with an actionable message.

    An unconfigured install is the common case for a first run, so it gets its
    own message pointing at ``doctor`` rather than a parse error.
    """
    manager = ConfigManager(config_path=Path(config_path) if config_path else None)

    if not manager.exists():
        typer.echo("No AI provider is configured.")
        typer.echo("")
        typer.echo("Run `resume-tailor doctor` to configure a provider.")
        raise typer.Exit(code=1)

    try:
        return manager.load()
    except ConfigError as exc:
        fail(f"Failed to load configuration: {exc}")


def build_provider(
    config: ResumeTailorConfig,
    credential_manager: Optional[CredentialManager] = None,
) -> LLMProvider:
    """
    Construct the configured provider, or exit with a message.

    One provider per run, handed to every stage, so a run cannot silently mix
    models between analysis, planning and generation.
    """
    credentials = (
        credential_manager if credential_manager is not None else CredentialManager()
    )
    try:
        return ProviderFactory.create(config, credentials)
    except AuthenticationError as exc:
        fail(f"Authentication failed: {exc}")
    except ConnectionError as exc:
        fail(f"Connection failed: {exc}")
    except ProviderError as exc:
        fail(f"Provider error: {exc}")


# ---------------------------------------------------------------------------
# Job description input
# ---------------------------------------------------------------------------


def read_job_description(jd_path: Optional[str] = None) -> str:
    """
    Read a job description from a file, or from a paste on stdin.

    Pasting is the original workflow and stays the default: a banner, then
    everything up to EOF. There is no size limit and no temporary file -- a job
    description is a few kilobytes of text and belongs in memory.
    """
    if jd_path is not None:
        return _read_job_description_file(jd_path)
    return _read_job_description_stdin()


def _read_job_description_file(jd_path: str) -> str:
    """Read and validate a job description held in a file."""
    try:
        text = Path(jd_path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        fail(f"Failed to read the job description file: {exc}")

    if not text:
        fail("The job description is empty.")
    return text


def _read_job_description_stdin() -> str:
    """Prompt the user to paste a job description and read until EOF."""
    typer.echo("Paste the job description below.")
    typer.echo("")
    typer.echo("Press Ctrl+D (Ctrl+Z on Windows) when finished.")
    typer.echo("")
    typer.echo("-" * 50)

    lines: List[str] = []
    try:
        for line in sys.stdin:
            lines.append(line)
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("Cancelled.")
        raise typer.Exit(code=1)

    text = "".join(lines).strip()
    if not text:
        typer.echo("")
        fail("No job description provided. Please paste a job description.")
    return text


# ---------------------------------------------------------------------------
# The LLM error ladder
# ---------------------------------------------------------------------------

#: ``(exception type, headline, follow-up lines)``. A headline containing
#: ``{exc}`` is formatted with the exception and printed alone; one without it
#: is printed as a heading with the exception indented beneath, which is how
#: the long parser and schema messages stay readable.
#:
#: **Order is load-bearing and every subclass precedes its base.** Walked with
#: ``isinstance``, first match wins.
_ARMS: Tuple[Tuple[Type[BaseException], str, Tuple[str, ...]], ...] = (
    (
        InvalidPlannerResponse,
        "The AI provider returned an empty or unexpected response.",
        (),
    ),
    (InvalidPlannerJSON, "The AI provider returned invalid JSON.", ()),
    (ResumePlanValidationError, "The plan did not match the expected structure.", ()),
    (PlanConsistencyError, "The plan is inconsistent with the resume.", ()),
    (PlannerError, "Planner error: {exc}", ()),
    (
        InvalidAnalyzerResponse,
        "The AI provider returned an empty or unexpected response.",
        (),
    ),
    (InvalidAnalyzerJSON, "The AI provider returned invalid JSON.", ()),
    (
        MissingJobRole,
        "No job title found in the job description.",
        (
            "",
            "Every other field can be inferred from the body text, but the",
            "title usually lives in the page heading and is lost on a copy",
            "and paste. Add it as the first line, for example:",
            "",
            "    Senior Software Engineer, Platform",
            "",
        ),
    ),
    (
        JobAnalysisValidationError,
        "The response did not match the expected structure.",
        (),
    ),
    (AnalyzerError, "Analyzer error: {exc}", ()),
    (AuthenticationError, "Authentication failed: {exc}", ()),
    (
        ConnectionError,
        "Connection failed: {exc}",
        ("", "Verify that the provider is running and reachable."),
    ),
    (RateLimitError, "Rate limit exceeded: {exc}", ()),
    (ProviderResponseError, "Provider response error: {exc}", ()),
    (ProviderError, "Provider error: {exc}", ()),
)

#: What ``llm_error_ladder`` catches, and what a command should name in its own
#: ``except`` clause when it delegates to ``report_llm_error``.
LLM_ERRORS: Tuple[Type[BaseException], ...] = (
    AnalyzerError,
    PlannerError,
    ProviderError,
)


def report_llm_error(exc: BaseException) -> bool:
    """
    Echo the message for a known analyzer, planner or provider error.

    Returns ``False`` when nothing in the table matches, so a caller can
    re-raise rather than swallow an exception it does not understand.
    """
    for arm, headline, extra in _ARMS:
        if isinstance(exc, arm):
            if "{exc}" in headline:
                typer.echo(f"{FAILURE_GLYPH} {headline.format(exc=exc)}")
            else:
                typer.echo(f"{FAILURE_GLYPH} {headline}")
                typer.echo(f"  {exc}")
            for line in extra:
                typer.echo(line)
            return True
    return False


@contextmanager
def llm_error_ladder() -> Iterator[None]:
    """
    Turn any analyzer, planner or provider failure into a message and exit 1.

    Wrap the LLM-driven part of a command in this. Anything unrecognised
    propagates untouched, because a stack trace beats a wrong diagnosis.
    """
    try:
        yield
    except LLM_ERRORS as exc:
        if not report_llm_error(exc):
            raise
        raise typer.Exit(code=1)
