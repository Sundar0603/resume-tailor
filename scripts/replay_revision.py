"""
Replay the Revision Engine over every generated resume already on disk.

Real renderer, real pdflatex, real Quality Gate, **zero LLM calls** — the
resumes were produced by earlier live runs and are reloaded from
``output/runs/<name>/04_generated_resume.json``, so this exercises the whole
convergence loop against genuine model output without paying for inference.

That matters because §9 lesson 6 of ``docs/PROJECT_KNOWLEDGE.md`` is the
project's most expensive lesson: offline tests are not evidence. This is the
cheap half of the evidence — the half that needs no provider.

Usage::

    PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH" \
        .venv/bin/python scripts/replay_revision.py

Not collected by pytest.
"""

import json
import sys
import time
from pathlib import Path

from src.compiler.exceptions import CompilationFailedError
from src.compiler.pdf_compiler import PDFCompiler
from src.parser.models import Resume
from src.quality.quality_gate import QualityGate
from src.renderer.latex_renderer import LatexRenderer
from src.revision import RevisionEngine, freeable_lines
from src.revision.exceptions import RevisionError

RUNS = Path("output/runs")
REPLAY = Path("output/replay")


def judge(resume: Resume, directory: Path):
    """Render, compile and judge one resume; return its Quality Gate verdict."""
    latex = LatexRenderer().render(resume)
    compiler = PDFCompiler()
    gate = QualityGate()
    try:
        compilation = compiler.compile(latex, output_directory=str(directory), job_name="before")
    except CompilationFailedError as failure:
        return gate.evaluate_compilation_failure(failure)
    return gate.evaluate(compilation.pdf_path, compilation.tex_path, compilation)


def replay(name: str) -> int:
    """Replay one run. Returns 0 when the engine delivered a passing resume."""
    payload = RUNS / name / "04_generated_resume.json"
    if not payload.is_file():
        print("{0:<28} no generated resume on disk, skipped".format(name))
        return 0

    resume = Resume.model_validate(json.loads(payload.read_text(encoding="utf-8")))
    destination = REPLAY / name
    destination.mkdir(parents=True, exist_ok=True)

    before = judge(resume, destination / "before")
    engine = RevisionEngine()          # provider=None: deterministic only

    started = time.time()
    try:
        result = engine.revise(
            source_resume=resume,
            current_resume=resume,
            quality_result=before,
            output_directory=str(destination),
        )
    except RevisionError as error:
        print(
            "{0:<28} FAILED  pages={1} spill={2} freeable={3}  {4}".format(
                name,
                before.metrics.page_count,
                before.metrics.overflow_line_count,
                freeable_lines(resume),
                error,
            )
        )
        return 1
    elapsed = time.time() - started

    print(
        "{0:<28} {1}  {2} -> 1 page  spill {3} -> {4}  "
        "steps={5} attempts={6} llm={7}  {8:.1f}s".format(
            name,
            "PASS" if result.passed else "FAIL",
            before.metrics.page_count,
            before.metrics.overflow_line_count,
            result.quality.metrics.overflow_line_count,
            result.deterministic_steps,
            result.attempts,
            result.llm_calls,
            elapsed,
        )
    )
    return 0 if result.passed else 1


def main() -> int:
    """Replay every run named on the command line, or every run on disk."""
    names = sys.argv[1:] or sorted(
        p.name for p in RUNS.iterdir() if (p / "04_generated_resume.json").is_file()
    )
    return max([replay(name) for name in names] or [0])


if __name__ == "__main__":
    raise SystemExit(main())
