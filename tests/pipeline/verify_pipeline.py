#!/usr/bin/env python
"""
Live end-to-end check: a real provider, a real job description, a real PDF.

Not collected by pytest (the name does not match ``test_*.py``), matching the
other ``verify_*.py`` scripts.

This exists because of §9 lesson 6: *offline tests are not evidence*. The
planner once shipped with 318 green tests while every real invocation failed.
The offline chain test proves the stages fit together; only this proves the
chain survives a real model's output.

Usage::

    .venv/bin/python tests/pipeline/verify_pipeline.py
    .venv/bin/python tests/pipeline/verify_pipeline.py --mode AGGRESSIVE \
        --resume content/fullstack_resume.md \
        --jd tests/fixtures/job_descriptions/fullstack.md

Needs a configured provider and, for the compile and quality stages, pdflatex
on PATH.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config.manager import ConfigManager  # noqa: E402
from src.config.credentials import CredentialManager  # noqa: E402
from src.parser import ResumeParser  # noqa: E402
from src.pipeline import ResumePipeline  # noqa: E402
from src.planner.models import PlanningMode  # noqa: E402
from src.providers.factory import ProviderFactory  # noqa: E402

DEFAULT_RESUME = "content/backend_resume.md"
DEFAULT_JD = "tests/fixtures/job_descriptions/backend.md"
DEFAULT_OUTPUT = "output/runs/verify"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", default=DEFAULT_RESUME)
    parser.add_argument("--jd", default=DEFAULT_JD)
    parser.add_argument("--mode", default="STRICT")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if shutil.which("pdflatex") is None:
        print("! pdflatex is not on PATH — compile and quality stages will fail.")
        print("  Try: export PATH=\"$HOME/Library/TinyTeX/bin/universal-darwin:$PATH\"")

    config = ConfigManager().load()
    provider = ProviderFactory.create(config, CredentialManager())
    mode = PlanningMode.parse(args.mode)

    resume = ResumeParser().parse(args.resume)
    job_description = Path(args.jd).read_text(encoding="utf-8")

    print("resume : {0}".format(args.resume))
    print("job    : {0}".format(args.jd))
    print("mode   : {0}\n".format(mode.value))

    started = time.time()
    result = ResumePipeline(provider).run(
        source_resume=resume,
        job_description=job_description,
        mode=mode,
        output_directory=args.output,
    )
    elapsed = time.time() - started

    quality = result.quality
    metrics = quality.metrics
    print("role detected      : {0}".format(result.job_analysis.role))
    print("keywords           : {0}".format(", ".join(result.job_analysis.keywords[:8])))
    print("pdf                : {0}".format(result.pdf_path))
    print("pages              : {0}".format(metrics.page_count))
    print("overfull / glyphs  : {0} / {1}".format(
        metrics.overfull_hbox_count, metrics.missing_glyph_count))
    print("overlap / orphans  : {0} / {1}".format(
        metrics.overlap_count, metrics.orphan_word_count))
    print("overflow           : {0} lines from {1}".format(
        metrics.overflow_line_count,
        ", ".join(s.value for s in metrics.overflowing_sections) or "-"))
    print("errors / warnings  : {0} / {1}".format(
        len(quality.errors), len(quality.warnings)))
    print("elapsed            : {0:.1f}s".format(elapsed))

    for issue in quality.issues:
        print("  [{0}] {1}".format(issue.severity.value, issue.message[:88]))

    print("\nPASSED" if result.passed else "\nFAILED (expected until the Revision Engine exists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
