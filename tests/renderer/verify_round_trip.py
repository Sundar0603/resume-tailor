"""
Live round-trip check for the Markdown Serializer.

The offline suite round-trips hand-built resumes and the three canonical files
in ``content/``. This script covers the case none of them reach: a resume that
the *real* Generator produced, carrying GENERATED entities, minted ids, model
prose and whatever vocabulary the model chose.

That gap is the one PROJECT_KNOWLEDGE §9 lesson 6 keeps warning about — the
planner shipped with 318 green offline tests while every live invocation
failed. The serializer makes no LLM call, so its own logic is fully covered
offline; what is not covered offline is the *input*, and only a live
generation produces a realistic one.

Deliberately named ``verify_*`` rather than ``test_*`` so pytest does not
collect it — it needs a running provider and takes a minute or more per mode.

Usage::

    python tests/renderer/verify_round_trip.py --resume content/backend_resume.md \\
        --jd tests/fixtures/job_descriptions/backend.md
    python tests/renderer/verify_round_trip.py --resume content/backend_resume.md \\
        --jd tests/fixtures/job_descriptions/backend.md --mode aggressive

Checks performed per mode:

- Serialization completes without raising.
- Serialization is byte-identical when repeated.
- The generated resume is byte-identical afterwards (no mutation).
- Re-parsing the output succeeds.
- The re-parsed resume is semantically equal to the generated one, ignoring
  the runtime-only ``id`` and ``source`` fields.
- No runtime metadata leaked into the document.
- The re-parsed resume still passes ResumeValidator against the source.

Exit status is 0 when every requested mode passes, 1 otherwise.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analyzer import JDAnalyzer  # noqa: E402
from src.config.credentials import CredentialManager  # noqa: E402
from src.config.manager import ConfigManager  # noqa: E402
from src.generator import ResumeGenerator  # noqa: E402
from src.parser import ResumeParser  # noqa: E402
from src.parser.models import Resume  # noqa: E402
from src.planner import ResumePlanner  # noqa: E402
from src.planner.models import PlanningMode  # noqa: E402
from src.providers.factory import ProviderFactory  # noqa: E402
from src.renderer import MarkdownSerializer  # noqa: E402
from src.validation import ResumeValidator  # noqa: E402

RUNTIME_FIELDS = ("id", "source")
LEAKED_TOKENS = ("CANONICAL", "GENERATED", "source:", "exp_0", "proj_0", "skill_0", "edu_0")


def semantic_dump(resume: Resume) -> Dict[str, Any]:
    """Dump a resume with the runtime-only fields removed."""
    data = resume.model_dump()
    for key in ("skills", "experiences", "projects", "education"):
        for entity in data[key]:
            for field in RUNTIME_FIELDS:
                entity.pop(field, None)
    return data


def check(label: str, passed: bool) -> bool:
    """Print one check line and return its result."""
    print("  {} {}".format("PASS" if passed else "FAIL", label))
    return passed


def run_mode(provider, source: Resume, job_description: str, mode) -> bool:
    """Generate in one mode, round-trip the result, and report."""
    print("\n=== {} ===".format(mode.value))
    started = time.time()

    analysis = JDAnalyzer(provider).analyze(job_description)
    plan = ResumePlanner(provider).plan(
        resume=source, job_analysis=analysis, mode=mode
    )
    generated = ResumeGenerator(provider).generate(
        source_resume=source, job_analysis=analysis, resume_plan=plan, mode=mode
    )
    print("  generated in {:.0f}s".format(time.time() - started))

    serializer, parser = MarkdownSerializer(), ResumeParser()
    before = generated.model_dump()
    markdown = serializer.serialize(generated)

    results = [
        check("serialization is deterministic", serializer.serialize(generated) == markdown),
        check("generated resume was not mutated", generated.model_dump() == before),
    ]

    reparsed = parser.parse_string(markdown)
    results.append(check("output re-parses", isinstance(reparsed, Resume)))
    results.append(
        check(
            "re-parsed resume is semantically equal",
            semantic_dump(reparsed) == semantic_dump(generated),
        )
    )

    leaked = [token for token in LEAKED_TOKENS if token in markdown]
    results.append(check("no runtime metadata leaked {}".format(leaked or ""), not leaked))

    result = ResumeValidator().validate(
        source_resume=source, generated_resume=reparsed, mode=mode
    )
    results.append(
        check(
            "re-parsed resume passes the validator ({} errors)".format(
                len(result.errors)
            ),
            result.is_valid,
        )
    )
    for warning in result.warnings:
        print("  warning: {}".format(warning.message))

    generated_entities = sum(
        1
        for group in (generated.projects, generated.skills)
        for entity in group
        if entity.source.value == "GENERATED"
    )
    print("  generated entities in this run: {}".format(generated_entities))
    if not generated_entities:
        print("  note: nothing was GENERATED, so the source-loss path went unexercised.")

    return all(results)


def main() -> int:
    """Parse arguments, run each requested mode, and report overall status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", required=True, help="Path to a Markdown resume")
    parser.add_argument("--jd", required=True, help="Path to a job description file")
    parser.add_argument(
        "--mode", default="both", help="strict, aggressive, or both (default: both)"
    )
    args = parser.parse_args()

    if args.mode.strip().casefold() == "both":
        modes = [PlanningMode.STRICT, PlanningMode.AGGRESSIVE]
    else:
        modes = [PlanningMode.parse(args.mode)]

    config = ConfigManager().load()
    provider = ProviderFactory.create(config, CredentialManager())
    source = ResumeParser().parse(args.resume)
    job_description = Path(args.jd).read_text(encoding="utf-8").strip()

    print("model            {}".format(config.model))
    print("resume           {}".format(args.resume))
    print("jd               {}".format(args.jd))

    results = [run_mode(provider, source, job_description, mode) for mode in modes]

    print()
    if all(results):
        print("PASS: every mode round-tripped cleanly.")
        return 0
    print("FAIL: at least one mode did not round-trip.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
