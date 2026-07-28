"""
Analyze command for Resume Tailor.

Prompts the user to paste a job description, invokes the JDAnalyzer,
and pretty-prints the resulting JobAnalysis.

The CLI communicates exclusively with:
    - ConfigManager
    - CredentialManager
    - ProviderFactory
    - JDAnalyzer

It never constructs prompts, parses JSON, or validates JobAnalysis directly.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer

from src.analyzer import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JDAnalyzer,
    JobAnalysis,
    JobAnalysisValidationError,
)
from src.config.credentials import CredentialManager
from src.config.exceptions import ConfigError
from src.config.manager import ConfigManager
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.factory import ProviderFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_header() -> None:
    typer.echo("")
    typer.echo("Job Description Analyzer")
    typer.echo("")


def _print_section(title: str) -> None:
    typer.echo("")
    typer.echo(title)
    typer.echo("-" * len(title))


def _print_list(items: list) -> None:
    if not items:
        typer.echo("  (none)")
        return
    for item in items:
        typer.echo(f"  \u2022 {item}")


def _read_job_description() -> str:
    """Prompt the user to paste a job description and read until EOF."""
    typer.echo("Paste the job description below.")
    typer.echo("")
    typer.echo("Press Ctrl+D (Ctrl+Z on Windows) when finished.")
    typer.echo("")
    typer.echo("-" * 50)

    lines = []
    try:
        for line in sys.stdin:
            lines.append(line)
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("Cancelled.")
        raise typer.Exit(code=1)

    return "".join(lines).strip()


def _pretty_print(analysis: JobAnalysis) -> None:
    """Pretty-print a JobAnalysis in a human-readable format."""
    typer.echo("")
    typer.echo("Job Analysis")
    typer.echo("=" * 12)

    if analysis.company:
        _print_section("Company")
        typer.echo(f"  {analysis.company}")

    _print_section("Role")
    typer.echo(f"  {analysis.role}")

    if analysis.seniority:
        _print_section("Seniority")
        typer.echo(f"  {analysis.seniority}")

    _print_section("Summary")
    typer.echo(f"  {analysis.summary}")

    _print_section("Required Skills")
    _print_list(analysis.required_skills)

    if analysis.preferred_skills:
        _print_section("Preferred Skills")
        _print_list(analysis.preferred_skills)

    if analysis.technologies:
        _print_section("Technologies")
        _print_list(analysis.technologies)

    if analysis.domains:
        _print_section("Domains")
        _print_list(analysis.domains)

    if analysis.responsibilities:
        _print_section("Responsibilities")
        _print_list(analysis.responsibilities)

    if analysis.qualifications:
        _print_section("Qualifications")
        _print_list(analysis.qualifications)

    if analysis.nice_to_have:
        _print_section("Nice To Have")
        _print_list(analysis.nice_to_have)

    if analysis.keywords:
        _print_section("Keywords")
        _print_list(analysis.keywords)

    typer.echo("")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def analyze(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        help="Override the default configuration file path.",
        hidden=True,
    ),
) -> None:
    """
    Analyze a job description using the configured AI provider.
    """
    from pathlib import Path

    _print_header()

    # --- Load configuration ---
    config_manager = ConfigManager(
        config_path=Path(config_path) if config_path else None
    )
    credential_manager = CredentialManager()

    if not config_manager.exists():
        typer.echo("No AI provider is configured.")
        typer.echo("")
        typer.echo("Run `resume-tailor doctor` to configure a provider.")
        raise typer.Exit(code=1)

    try:
        config = config_manager.load()
    except ConfigError as exc:
        typer.echo(f"\u2717 Failed to load configuration: {exc}")
        raise typer.Exit(code=1)

    # --- Read job description ---
    job_description = _read_job_description()

    if not job_description:
        typer.echo("")
        typer.echo("\u2717 No job description provided. Please paste a job description.")
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Analyzing job description...")
    typer.echo("")

    # --- Construct provider and analyzer ---
    try:
        provider = ProviderFactory.create(config, credential_manager)
    except AuthenticationError as exc:
        typer.echo(f"\u2717 Authentication failed: {exc}")
        raise typer.Exit(code=1)
    except ConnectionError as exc:
        typer.echo(f"\u2717 Connection failed: {exc}")
        raise typer.Exit(code=1)
    except ProviderError as exc:
        typer.echo(f"\u2717 Provider error: {exc}")
        raise typer.Exit(code=1)

    analyzer = JDAnalyzer(provider=provider)

    # --- Run analysis ---
    try:
        analysis = analyzer.analyze(job_description)
    except InvalidAnalyzerResponse as exc:
        typer.echo("\u2717 The AI provider returned an empty or unexpected response.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except InvalidAnalyzerJSON as exc:
        typer.echo("\u2717 The AI provider returned invalid JSON.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except JobAnalysisValidationError as exc:
        typer.echo("\u2717 The response did not match the expected structure.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except AuthenticationError as exc:
        typer.echo(f"\u2717 Authentication failed: {exc}")
        raise typer.Exit(code=1)
    except ConnectionError as exc:
        typer.echo(f"\u2717 Connection failed: {exc}")
        typer.echo("")
        typer.echo("Verify that the provider is running and reachable.")
        raise typer.Exit(code=1)
    except RateLimitError as exc:
        typer.echo(f"\u2717 Rate limit exceeded: {exc}")
        raise typer.Exit(code=1)
    except ProviderResponseError as exc:
        typer.echo(f"\u2717 Provider response error: {exc}")
        raise typer.Exit(code=1)
    except ProviderError as exc:
        typer.echo(f"\u2717 Provider error: {exc}")
        raise typer.Exit(code=1)
    except AnalyzerError as exc:
        typer.echo(f"\u2717 Analyzer error: {exc}")
        raise typer.Exit(code=1)

    # --- Display result ---
    _pretty_print(analysis)
