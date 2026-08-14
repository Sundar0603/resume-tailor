"""
Live generation check for the Resume Generator.

The offline suite feeds the generator scripted responses. This script is the
other half: it drives the *real* configured provider end to end — parse,
analyze, plan, generate — and reports whether the result holds up.

This exists because of what the Planner build taught us: 318 offline tests
passed while every real invocation failed. Mocked tests prove the assembly
logic; only a live run proves the prompts work on the model we actually ship
against.

Deliberately named ``verify_*`` rather than ``test_*`` so pytest does not
collect it — it needs a running provider and takes a minute or more per mode.

Usage::

    python tests/generator/verify_generation.py --resume content/backend_resume.md \\
        --jd tests/fixtures/job_descriptions/backend.md
    python tests/generator/verify_generation.py --resume content/backend_resume.md \\
        --jd tests/fixtures/job_descriptions/backend.md --mode aggressive

The job description is read with ``.strip()`` to match ``src/cli/plan.py``.

Checks performed per mode:

- Generation completes without raising.
- The validator reports zero errors (warnings are printed, not failed on).
- The source resume is byte-identical afterwards.
- Contact, education and metadata match the source.
- Exactly two experiences, at least two projects.
- STRICT only: no technology, skill or number absent from the source.
- AGGRESSIVE only: reports whether any role was retitled.

Exit status is 0 when every requested mode passes, 1 otherwise.
"""

import argparse
import copy
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analyzer import JDAnalyzer  # noqa: E402
from src.config.credentials import CredentialManager  # noqa: E402
from src.config.manager import ConfigManager  # noqa: E402
from src.generator import GeneratorError, ResumeGenerator  # noqa: E402
from src.generator.constraints import enforce_strict  # noqa: E402
from src.parser import ResumeParser  # noqa: E402
from src.parser.models import EntitySource, Resume  # noqa: E402
from src.planner import ResumePlanner  # noqa: E402
from src.planner.models import PlanningMode  # noqa: E402
from src.providers.factory import ProviderFactory  # noqa: E402


def summarize(resume: Resume) -> None:
    """Print a short shape report for a generated resume."""
    generated_projects = [
        p for p in resume.projects if p.source == EntitySource.GENERATED
    ]
    generated_categories = [
        c for c in resume.skills if c.source == EntitySource.GENERATED
    ]
    print(f"  summary          {len(resume.summary.split())} words")
    print(f"  skill categories {len(resume.skills)} "
          f"({len(generated_categories)} generated)")
    print(f"  experiences      {len(resume.experiences)}")
    print(f"  projects         {len(resume.projects)} "
          f"({len(generated_projects)} generated)")


def check_structure(source: Resume, generated: Resume) -> List[str]:
    """Return a list of structural problems, empty when all is well."""
    problems: List[str] = []

    if generated.contact != source.contact:
        problems.append("contact was modified")
    if generated.education != source.education:
        problems.append("education was modified")
    if generated.metadata != source.metadata:
        problems.append("metadata was modified")
    if len(generated.experiences) != 2:
        problems.append(f"expected 2 experiences, got {len(generated.experiences)}")
    if len(generated.projects) < 2:
        problems.append(f"expected at least 2 projects, got {len(generated.projects)}")

    for src_exp, gen_exp in zip(source.experiences, generated.experiences):
        for field in ("company", "duration", "employment_type", "location"):
            if getattr(src_exp, field) != getattr(gen_exp, field):
                problems.append(f"{gen_exp.id}: {field} was modified")

    ids = [e.id for e in generated.experiences]
    ids += [p.id for p in generated.projects]
    ids += [c.id for c in generated.skills]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        problems.append("entity ids are missing or not unique")

    return problems


def report_roles(source: Resume, generated: Resume) -> None:
    """Print any role retitling, which aggressive mode permits."""
    for src_exp, gen_exp in zip(source.experiences, generated.experiences):
        if src_exp.role != gen_exp.role:
            print(f"  retitled         {src_exp.role!r} -> {gen_exp.role!r}")


def run_mode(provider, resume: Resume, job_description: str, mode: PlanningMode) -> bool:
    """Run one full generation and report on it. Returns True on success."""
    print()
    print(f"=== {mode.value} ===")

    before = copy.deepcopy(resume)
    started = time.time()

    try:
        analysis = JDAnalyzer(provider=provider).analyze(job_description)
        plan = ResumePlanner(provider=provider).plan(resume, analysis, mode)
        generator = ResumeGenerator(provider=provider)
        generated = generator.generate(
            source_resume=resume,
            job_analysis=analysis,
            resume_plan=plan,
        )
    except GeneratorError as exc:
        print(f"  FAILED after {time.time() - started:.1f}s")
        print(f"  {type(exc).__name__}: {exc}")
        return False

    elapsed = time.time() - started
    print(f"  completed        {elapsed:.1f}s")
    summarize(generated)

    problems = check_structure(resume, generated)

    if resume != before:
        problems.append("the source resume was mutated")

    if mode == PlanningMode.AGGRESSIVE:
        report_roles(resume, generated)
    else:
        # The generator already enforced this; re-running it here proves the
        # check ran rather than being skipped by a mode mix-up.
        try:
            enforce_strict(resume, generated)
            print("  strict check     no fabricated terms or metrics")
        except GeneratorError as exc:
            problems.append(f"strict violation survived: {exc}")

    for warning in generator.last_warnings:
        print(f"  warning          {warning.code.value}: {warning.message}")
    for discarded in generator.last_discarded:
        print(f"  discarded        {discarded}")

    if problems:
        for problem in problems:
            print(f"  PROBLEM          {problem}")
        return False

    print("  PASS")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", required=True, help="Path to a resume markdown file")
    parser.add_argument("--jd", required=True, help="Path to a job description file")
    parser.add_argument(
        "--mode",
        default="both",
        help="strict, aggressive, or both (default: both)",
    )
    args = parser.parse_args()

    if args.mode.strip().casefold() == "both":
        modes = [PlanningMode.STRICT, PlanningMode.AGGRESSIVE]
    else:
        modes = [PlanningMode.parse(args.mode)]

    config = ConfigManager().load()
    provider = ProviderFactory.create(config, CredentialManager())
    resume = ResumeParser().parse(args.resume)
    # Matches src/cli/plan.py exactly.
    job_description = Path(args.jd).read_text(encoding="utf-8").strip()

    print(f"model            {config.model}")
    print(f"resume           {args.resume}")
    print(f"jd               {args.jd}")

    results = [run_mode(provider, resume, job_description, mode) for mode in modes]

    print()
    if all(results):
        print("PASS: every mode produced a valid resume.")
        return 0
    print("FAIL: at least one mode did not produce a valid resume.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
