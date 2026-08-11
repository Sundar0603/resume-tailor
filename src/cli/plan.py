"""
Plan command for Resume Tailor.

Reads a resume and a job description, runs the Job Description Analyzer and
then the Resume Planner, and pretty-prints the resulting ResumePlan.

This is a debug view of the middle stage of the pipeline. The ResumePlan is
never written to disk.

The CLI communicates exclusively with:
    - ConfigManager
    - CredentialManager
    - ProviderFactory
    - ResumeParser
    - JDAnalyzer
    - ResumePlanner

It never constructs prompts, parses JSON, or validates a ResumePlan directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from src.analyzer import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JDAnalyzer,
    JobAnalysisValidationError,
)
from src.config.credentials import CredentialManager
from src.config.exceptions import ConfigError
from src.config.manager import ConfigManager
from src.parser import ParserError, Resume, ResumeParser
from src.planner import (
    InvalidPlannerJSON,
    InvalidPlannerResponse,
    PlanConsistencyError,
    PlannerError,
    ResumePlan,
    ResumePlanner,
    ResumePlanValidationError,
    UnknownPlanningMode,
)
from src.planner.models import PlanningMode
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.factory import ProviderFactory

# ---------------------------------------------------------------------------
# Printer helpers
# ---------------------------------------------------------------------------


def _print_header() -> None:
    typer.echo("")
    typer.echo("Resume Planner")
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
        typer.echo(f"  • {item}")


def _print_field(label: str, value) -> None:
    if value is None:
        return
    typer.echo(f"  {label}: {value}")


def _print_divider() -> None:
    typer.echo("")
    typer.echo("  " + "-" * 40)


def _experience_label(resume: Resume, experience_id: str) -> str:
    for experience in resume.experiences:
        if experience.id == experience_id:
            return f"{experience.company} ({experience.role})"
    return experience_id


def _project_label(resume: Resume, project_id: Optional[str]) -> str:
    if project_id is None:
        return "New project"
    for project in resume.projects:
        if project.id == project_id:
            return project.name
    return project_id


def _category_label(resume: Resume, category_id: Optional[str]) -> str:
    if category_id is None:
        return "New category"
    for category in resume.skills:
        if category.id == category_id:
            return category.category
    return category_id


def _pretty_print(plan: ResumePlan, resume: Resume, discarded: list) -> None:
    """Pretty-print a ResumePlan in a human-readable format."""
    typer.echo("")
    typer.echo("Resume Plan")
    typer.echo("=" * 11)
    typer.echo(f"Mode: {plan.mode.value}")

    _print_section("Summary")
    _print_field("Action", plan.summary_plan.action.value)
    _print_field("Priority", plan.summary_plan.priority.name)
    _print_field("Reasoning", plan.summary_plan.reasoning)
    if plan.summary_plan.keywords_to_include:
        typer.echo("  Keywords to include:")
        _print_list(plan.summary_plan.keywords_to_include)

    _print_section("Experience")
    for ep in plan.experience_plans:
        typer.echo(f"  {_experience_label(resume, ep.experience_id)}")
        _print_field("    Action", ep.action.value)
        _print_field("    Priority", ep.priority.name)
        _print_field("    Rewrite strategy", ep.rewrite_strategy)
        _print_field("    Reasoning", ep.reasoning)
        if ep.keywords_to_include:
            typer.echo("    Keywords to include:")
            _print_list(ep.keywords_to_include)
        if ep.themes_to_emphasize:
            typer.echo("    Themes to emphasize:")
            _print_list(ep.themes_to_emphasize)
        _print_divider()

    _print_section("Projects")
    for pp in plan.project_plans:
        typer.echo(f"  {_project_label(resume, pp.project_id)}")
        _print_field("    Action", pp.action.value)
        _print_field("    Priority", pp.priority.name)
        _print_field("    Rewrite strategy", pp.rewrite_strategy)
        _print_field("    Generation brief", pp.generation_brief)
        _print_field("    Reasoning", pp.reasoning)
        if pp.keywords_to_include:
            typer.echo("    Keywords to include:")
            _print_list(pp.keywords_to_include)
        if pp.themes_to_emphasize:
            typer.echo("    Themes to emphasize:")
            _print_list(pp.themes_to_emphasize)
        _print_divider()

    _print_section("Skills")
    for sp in plan.skills_plans:
        typer.echo(f"  {_category_label(resume, sp.category_id)}")
        _print_field("    Action", sp.action.value)
        _print_field("    Priority", sp.priority.name)
        _print_field("    New category name", sp.new_category_name)
        _print_field("    Reasoning", sp.reasoning)
        if sp.skills_to_add:
            typer.echo("    Skills to add:")
            _print_list(sp.skills_to_add)
        if sp.skills_to_remove:
            typer.echo("    Skills to remove:")
            _print_list(sp.skills_to_remove)
        _print_divider()

    if discarded:
        _print_section("Discarded")
        _print_list(discarded)

    typer.echo("")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def plan(
    resume: str = typer.Option(..., "--resume", help="Path to the resume Markdown file."),
    jd: str = typer.Option(..., "--jd", help="Path to the job description text file."),
    mode: str = typer.Option(
        "aggressive", "--mode", help="Planning mode: aggressive or strict."
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        help="Override the default configuration file path.",
        hidden=True,
    ),
) -> None:
    """
    Plan how a resume should be reshaped to fit a job description.
    """
    _print_header()

    try:
        resolved_mode = PlanningMode.parse(mode)
    except UnknownPlanningMode as exc:
        typer.echo(f"✗ {exc}")
        raise typer.Exit(code=1)

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
        typer.echo(f"✗ Failed to load configuration: {exc}")
        raise typer.Exit(code=1)

    # --- Parse the resume ---
    try:
        parsed_resume = ResumeParser().parse(resume)
    except ParserError as exc:
        typer.echo(f"✗ Failed to parse resume: {exc}")
        raise typer.Exit(code=1)
    except FileNotFoundError as exc:
        typer.echo(f"✗ Resume file not found: {exc}")
        raise typer.Exit(code=1)

    # --- Read the job description ---
    try:
        job_description = Path(jd).read_text(encoding="utf-8").strip()
    except OSError as exc:
        typer.echo(f"✗ Failed to read job description file: {exc}")
        raise typer.Exit(code=1)

    if not job_description:
        typer.echo("✗ Job description file is empty.")
        raise typer.Exit(code=1)

    typer.echo("Analyzing job description and building the plan...")
    typer.echo("")

    # --- Construct provider ---
    try:
        provider = ProviderFactory.create(config, credential_manager)
    except AuthenticationError as exc:
        typer.echo(f"✗ Authentication failed: {exc}")
        raise typer.Exit(code=1)
    except ConnectionError as exc:
        typer.echo(f"✗ Connection failed: {exc}")
        raise typer.Exit(code=1)
    except ProviderError as exc:
        typer.echo(f"✗ Provider error: {exc}")
        raise typer.Exit(code=1)

    analyzer = JDAnalyzer(provider=provider)
    planner = ResumePlanner(provider=provider)

    # --- Run analysis, then planning ---
    try:
        analysis = analyzer.analyze(job_description)
        resume_plan = planner.plan(parsed_resume, analysis, mode=resolved_mode)
    except InvalidPlannerResponse as exc:
        typer.echo("✗ The AI provider returned an empty or unexpected response.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except InvalidPlannerJSON as exc:
        typer.echo("✗ The AI provider returned invalid JSON.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except ResumePlanValidationError as exc:
        typer.echo("✗ The plan did not match the expected structure.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except PlanConsistencyError as exc:
        typer.echo("✗ The plan is inconsistent with the resume.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except PlannerError as exc:
        typer.echo(f"✗ Planner error: {exc}")
        raise typer.Exit(code=1)
    except InvalidAnalyzerResponse as exc:
        typer.echo("✗ The AI provider returned an empty or unexpected response.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except InvalidAnalyzerJSON as exc:
        typer.echo("✗ The AI provider returned invalid JSON.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except JobAnalysisValidationError as exc:
        typer.echo("✗ The response did not match the expected structure.")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except AnalyzerError as exc:
        typer.echo(f"✗ Analyzer error: {exc}")
        raise typer.Exit(code=1)
    except AuthenticationError as exc:
        typer.echo(f"✗ Authentication failed: {exc}")
        raise typer.Exit(code=1)
    except ConnectionError as exc:
        typer.echo(f"✗ Connection failed: {exc}")
        typer.echo("")
        typer.echo("Verify that the provider is running and reachable.")
        raise typer.Exit(code=1)
    except RateLimitError as exc:
        typer.echo(f"✗ Rate limit exceeded: {exc}")
        raise typer.Exit(code=1)
    except ProviderResponseError as exc:
        typer.echo(f"✗ Provider response error: {exc}")
        raise typer.Exit(code=1)
    except ProviderError as exc:
        typer.echo(f"✗ Provider error: {exc}")
        raise typer.Exit(code=1)

    # --- Display result ---
    _pretty_print(resume_plan, parsed_resume, planner.last_discarded)
