"""
Live determinism check for the Resume Planner.

The offline proof lives in ``test_determinism.py``; it feeds the planner
scripted responses and asserts that equivalent payloads collapse. This script
is the other half: it drives the *real* configured provider N times with one
resume and one job description, and asserts every run produces an identical
ResumePlan.

Deliberately named ``verify_*`` rather than ``test_*`` so pytest does not
collect it — it needs a running provider and takes ~30s per iteration.

Usage::

    python tests/planner/verify_determinism.py --resume content/backend_resume.md \
        --jd tests/fixtures/job_descriptions/backend.md
    python tests/planner/verify_determinism.py --resume content/backend_resume.md \
        --jd tests/fixtures/job_descriptions/backend.md --mode aggressive --iterations 5

The job description is read with ``.strip()`` to match ``src/cli/plan.py``
exactly. Reading it any other way changes the prompt and invalidates the
comparison.

Exit status is 0 when every iteration agrees, 1 otherwise.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analyzer import JDAnalyzer  # noqa: E402
from src.config.credentials import CredentialManager  # noqa: E402
from src.config.manager import ConfigManager  # noqa: E402
from src.parser import ResumeParser  # noqa: E402
from src.planner import ResumePlan, ResumePlanner  # noqa: E402
from src.planner.models import PlanningMode  # noqa: E402
from src.providers.factory import ProviderFactory  # noqa: E402


def fingerprint(plan: ResumePlan) -> str:
    """A stable, comparable serialization of a plan."""
    return json.dumps(plan.model_dump(), sort_keys=True, default=str)


def report(plans: List[ResumePlan]) -> bool:
    """Print a per-iteration comparison against the first run."""
    baseline = fingerprint(plans[0])
    print()
    print(f"{'iteration':<11} {'matches #1':<12} entries")
    print("-" * 38)

    all_match = True
    for index, plan in enumerate(plans, start=1):
        entries = (
            1
            + len(plan.experience_plans)
            + len(plan.project_plans)
            + len(plan.skills_plans)
        )
        matches = fingerprint(plan) == baseline
        all_match = all_match and matches
        print(f"{index:<11} {'yes' if matches else 'NO':<12} {entries}")

    if not all_match:
        print()
        print("Divergence detected. First differing iteration, field by field:")
        for index, plan in enumerate(plans[1:], start=2):
            if fingerprint(plan) == baseline:
                continue
            left = plans[0].model_dump()
            right = plan.model_dump()
            for key in left:
                if left[key] != right[key]:
                    print(f"  iteration {index}: {key} differs")
            break

    return all_match


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", required=True, help="Path to a resume markdown file")
    parser.add_argument("--jd", required=True, help="Path to a job description file")
    parser.add_argument(
        "--mode",
        default="strict",
        help="Planning mode: strict or aggressive (default: strict)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="How many times to plan (default: 3)",
    )
    args = parser.parse_args()

    mode = PlanningMode.parse(args.mode)
    config = ConfigManager().load()
    provider = ProviderFactory.create(config, CredentialManager())

    resume = ResumeParser().parse(args.resume)
    # Matches src/cli/plan.py — any other read changes the prompt.
    job_description = Path(args.jd).read_text(encoding="utf-8").strip()

    print(f"model      : {config.model}")
    print(f"mode       : {mode.value}")
    print(f"resume     : {args.resume}")
    print(f"jd         : {args.jd}")
    print(f"iterations : {args.iterations}")

    analysis = JDAnalyzer(provider=provider).analyze(job_description)
    planner = ResumePlanner(provider=provider)

    plans: List[ResumePlan] = []
    for index in range(args.iterations):
        started = time.time()
        plans.append(planner.plan(resume, analysis, mode=mode))
        print(f"  iteration {index + 1} planned in {time.time() - started:.0f}s")

    passed = report(plans)
    print()
    print("PASS: every iteration produced an identical plan" if passed else "FAIL: plans diverged")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
