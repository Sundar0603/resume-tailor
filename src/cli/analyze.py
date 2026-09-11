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

from typing import Optional

import typer

from src.analyzer import JDAnalyzer, JobAnalysis
from src.cli._common import (
    build_provider,
    llm_error_ladder,
    load_configuration,
    print_header,
    print_list,
    print_section,
    read_job_description,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pretty_print(analysis: JobAnalysis) -> None:
    """Pretty-print a JobAnalysis in a human-readable format."""
    typer.echo("")
    typer.echo("Job Analysis")
    typer.echo("=" * 12)

    if analysis.company:
        print_section("Company")
        typer.echo(f"  {analysis.company}")

    print_section("Role")
    if analysis.role_inferred:
        # The job description never stated a title; say so rather than let
        # a chosen one read as a quoted one.
        typer.echo(f"  {analysis.role}  (inferred - not stated in the job description)")
    else:
        typer.echo(f"  {analysis.role}")

    if analysis.seniority:
        print_section("Seniority")
        typer.echo(f"  {analysis.seniority}")

    print_section("Required Skills")
    print_list(analysis.required_skills)

    if analysis.preferred_skills:
        print_section("Preferred Skills")
        print_list(analysis.preferred_skills)

    if analysis.technologies:
        print_section("Technologies")
        print_list(analysis.technologies)

    if analysis.domains:
        print_section("Domains")
        print_list(analysis.domains)

    if analysis.responsibilities:
        print_section("Responsibilities")
        print_list(analysis.responsibilities)

    if analysis.qualifications:
        print_section("Qualifications")
        print_list(analysis.qualifications)

    if analysis.nice_to_have:
        print_section("Nice To Have")
        print_list(analysis.nice_to_have)

    if analysis.keywords:
        print_section("Keywords")
        print_list(analysis.keywords)

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
    print_header("Job Description Analyzer")

    config = load_configuration(config_path)
    job_description = read_job_description()

    typer.echo("")
    typer.echo("Analyzing job description...")
    typer.echo("")

    provider = build_provider(config)
    analyzer = JDAnalyzer(provider=provider)

    with llm_error_ladder():
        analysis = analyzer.analyze(job_description)

    # --- Display result ---
    _pretty_print(analysis)
