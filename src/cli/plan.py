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

from typing import Optional

import typer

from src.analyzer import JDAnalyzer
from src.cli._common import (
    build_provider,
    fail,
    llm_error_ladder,
    load_configuration,
    print_field,
    print_header,
    print_list,
    print_section,
    read_job_description,
)
from src.parser import ParserError, Resume, ResumeParser
from src.planner import ResumePlan, ResumePlanner, UnknownPlanningMode
from src.planner.models import PlanningMode

# ---------------------------------------------------------------------------
# Printer helpers
# ---------------------------------------------------------------------------


def _print_divider() -> None:
    """Separate one plan entry from the next. Local: only this command uses it."""
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

    print_section("Summary")
    print_field("Action", plan.summary_plan.action.value)
    print_field("Priority", plan.summary_plan.priority.name)
    print_field("Reasoning", plan.summary_plan.reasoning)
    if plan.summary_plan.keywords_to_include:
        typer.echo("  Keywords to include:")
        print_list(plan.summary_plan.keywords_to_include)

    print_section("Experience")
    for ep in plan.experience_plans:
        typer.echo(f"  {_experience_label(resume, ep.experience_id)}")
        print_field("    Action", ep.action.value)
        print_field("    Priority", ep.priority.name)
        print_field("    Rewrite strategy", ep.rewrite_strategy)
        print_field("    Reasoning", ep.reasoning)
        if ep.keywords_to_include:
            typer.echo("    Keywords to include:")
            print_list(ep.keywords_to_include)
        if ep.themes_to_emphasize:
            typer.echo("    Themes to emphasize:")
            print_list(ep.themes_to_emphasize)
        _print_divider()

    print_section("Projects")
    for pp in plan.project_plans:
        typer.echo(f"  {_project_label(resume, pp.project_id)}")
        print_field("    Action", pp.action.value)
        print_field("    Priority", pp.priority.name)
        print_field("    Rewrite strategy", pp.rewrite_strategy)
        print_field("    Generation brief", pp.generation_brief)
        print_field("    Reasoning", pp.reasoning)
        if pp.keywords_to_include:
            typer.echo("    Keywords to include:")
            print_list(pp.keywords_to_include)
        if pp.themes_to_emphasize:
            typer.echo("    Themes to emphasize:")
            print_list(pp.themes_to_emphasize)
        _print_divider()

    print_section("Skills")
    for sp in plan.skills_plans:
        typer.echo(f"  {_category_label(resume, sp.category_id)}")
        print_field("    Action", sp.action.value)
        print_field("    Priority", sp.priority.name)
        print_field("    New category name", sp.new_category_name)
        print_field("    Reasoning", sp.reasoning)
        if sp.skills_to_add:
            typer.echo("    Skills to add:")
            print_list(sp.skills_to_add)
        if sp.skills_to_remove:
            typer.echo("    Skills to remove:")
            print_list(sp.skills_to_remove)
        _print_divider()

    if discarded:
        print_section("Discarded")
        print_list(discarded)

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
    print_header("Resume Planner")

    try:
        resolved_mode = PlanningMode.parse(mode)
    except UnknownPlanningMode as exc:
        fail(str(exc))

    config = load_configuration(config_path)

    try:
        parsed_resume = ResumeParser().parse(resume)
    except ParserError as exc:
        fail(f"Failed to parse resume: {exc}")
    except FileNotFoundError as exc:
        # ResumeParser already raises a complete sentence ("Resume file not
        # found: <path>"), so prefixing it again would double the phrase.
        fail(str(exc))

    job_description = read_job_description(jd)

    typer.echo("Analyzing the job description and building a plan...")
    typer.echo("")

    provider = build_provider(config)
    analyzer = JDAnalyzer(provider=provider)
    planner = ResumePlanner(provider=provider)

    with llm_error_ladder():
        analysis = analyzer.analyze(job_description)
        resume_plan = planner.plan(parsed_resume, analysis, mode=resolved_mode)

    _pretty_print(resume_plan, parsed_resume, planner.last_discarded)
