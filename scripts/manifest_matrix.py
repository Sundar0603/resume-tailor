"""
Before/after matrix for the aggressive entry manifest.

3 pairings x 2 modes x 2 conditions x N trials.

BEFORE reproduces the shipped-as-of-2026-08-28 behaviour exactly: strict gets
the strict manifest, aggressive gets "". AFTER is whatever is in the tree now.

Pairings are chosen deliberately:
  backend+backend            - where the new aggressive failure was found
  cybersecurity+app-dev      - the pairing the original lesson-8 A/B used
  fullstack+fullstack        - a control that was never reported broken
"""
import sys, time
from collections import Counter
from pathlib import Path

from src.analyzer.analyzer import JDAnalyzer
from src.config.credentials import CredentialManager
from src.config.manager import ConfigManager
from src.parser import ResumeParser
from src.planner import prompts as pp
from src.planner.models import PlanningMode
from src.planner.planner import ResumePlanner
from src.providers.factory import ProviderFactory

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
PAIRINGS = [
    ("backend", "content/backend_resume.md",
     "tests/fixtures/job_descriptions/backend.md"),
    ("cyber+appdev", "content/cybersecurity_resume.md",
     "tests/fixtures/job_descriptions/application-software-developer.md"),
    ("fullstack", "content/fullstack_resume.md",
     "tests/fixtures/job_descriptions/fullstack.md"),
]

AFTER = pp._entry_manifest


def BEFORE(resume, mode):
    """The shipped behaviour before the fix."""
    if mode != PlanningMode.STRICT:
        return ""
    return pp._ENTRY_MANIFEST_TEMPLATE.format(
        skill_ids=", ".join(c.id for c in resume.skills),
        experience_count=len(resume.experiences),
        experience_ids=", ".join(e.id for e in resume.experiences),
        project_ids=", ".join(p.id for p in resume.projects),
    ) + "\n"


provider = ProviderFactory.create(ConfigManager().load(), CredentialManager())
planner = ResumePlanner(provider)
results = {}

for label, resume_path, jd_path in PAIRINGS:
    resume = ResumeParser().parse(resume_path)
    analysis = JDAnalyzer(provider).analyze(
        Path(jd_path).read_text(encoding="utf-8"))
    for condition, builder in (("before", BEFORE), ("after", AFTER)):
        pp._entry_manifest = builder
        for mode in (PlanningMode.STRICT, PlanningMode.AGGRESSIVE):
            outcomes = Counter()
            first_error = ""
            for _ in range(TRIALS):
                try:
                    planner.plan(resume, analysis, mode)
                    outcomes["ok"] += 1
                except Exception as error:
                    outcomes["fail"] += 1
                    if not first_error:
                        first_error = str(error).split("\n")[1:3]
                        first_error = " ".join(x.strip() for x in first_error)[:110]
            key = (label, condition, mode.value)
            results[key] = (outcomes["ok"], first_error)
            print("{0:14s} {1:7s} {2:10s} {3}/{4} ok   {5}".format(
                label, condition, mode.value, outcomes["ok"], TRIALS, first_error),
                flush=True)
        pp._entry_manifest = AFTER

print("\n=== MATRIX ({0} trials each) ===".format(TRIALS))
print("{0:14s} {1:10s} {2:>8s} {3:>8s}".format("pairing", "mode", "before", "after"))
for label, _, _ in PAIRINGS:
    for mode in ("STRICT", "AGGRESSIVE"):
        b = results.get((label, "before", mode), ("?",))[0]
        a = results.get((label, "after", mode), ("?",))[0]
        flag = ""
        if isinstance(b, int) and isinstance(a, int):
            if a > b:
                flag = "  IMPROVED"
            elif a < b:
                flag = "  REGRESSED"
        print("{0:14s} {1:10s} {2:>8} {3:>8}{4}".format(label, mode, b, a, flag))
