"""
Live render check for the LaTeX Renderer.

The offline suite covers the renderer's own logic against hand-built resumes.
What it cannot cover is a realistic *input*: model prose is where stray Unicode,
LaTeX specials, long bullets and odd punctuation actually appear. That is the
gap PROJECT_KNOWLEDGE §9 lesson 6 keeps warning about — offline tests are not
evidence.

Two modes of operation:

- ``--source-only`` parses the three canonical resumes and renders them. Fast,
  no provider, no LLM. Good for checking the templates themselves compile.
- The default drives the full pipeline (analyze → plan → generate → render)
  against the real provider, so the renderer sees generated content.

Deliberately named ``verify_*`` rather than ``test_*`` so pytest does not
collect it.

Usage::

    python tests/renderer/verify_latex_render.py --source-only
    python tests/renderer/verify_latex_render.py --resume content/backend_resume.md \\
        --jd tests/fixtures/job_descriptions/backend.md --mode aggressive

If pdflatex is on PATH each rendered document is compiled, which is the only
check that really proves the output is valid LaTeX. Without it the script still
verifies structure and reports that compilation was skipped.

Exit status is 0 when every check passes, 1 otherwise.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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
from src.renderer import LatexRenderer  # noqa: E402

CANONICAL_RESUMES = [
    "content/backend_resume.md",
    "content/cybersecurity_resume.md",
    "content/fullstack_resume.md",
]
LEAKED_TOKENS = ("CANONICAL", "GENERATED", "exp_0", "proj_0", "skill_0", "edu_0")


def check(label: str, passed: bool) -> bool:
    """Print one check line and return its result."""
    print("  {} {}".format("PASS" if passed else "FAIL", label))
    return passed


def compile_document(latex: str) -> bool:
    """
    Compile with pdflatex in a temporary directory.

    Reports the page count and any missing-glyph warnings. One page is the
    design's whole intent, so a second page is printed as a warning even though
    trimming to fit belongs to the Quality Gate rather than the renderer.
    """
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.tex"
        source.write_text(latex, encoding="utf-8")
        completed = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", source.name],
            cwd=directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log = completed.stdout.decode("utf-8", "replace")
        if not (Path(directory) / "resume.pdf").is_file():
            print("    pdflatex output tail:")
            for line in log.splitlines()[-25:]:
                print("      " + line)
            return False

        match = re.search(r"Output written on \S+ \((\d+) page", log)
        pages = int(match.group(1)) if match else 0
        print("    pages: {}".format(pages or "unknown"))
        if pages > 1:
            print("    warning: more than one page — the Quality Gate must trim.")
        if "Missing character" in log:
            print("    warning: pdflatex reported a missing character (glyph lost).")
        overfull = log.count("Overfull") + log.count("Underfull")
        if overfull:
            print("    note: {} overfull/underfull boxes".format(overfull))
        return True


def verify(resume: Resume, label: str, renderer: LatexRenderer) -> bool:
    """Render one resume and run every structural check on the result."""
    print("\n=== {} ===".format(label))
    before = resume.model_dump()
    latex = renderer.render(resume)

    results = [
        check("rendering is deterministic", renderer.render(resume) == latex),
        check("resume was not mutated", resume.model_dump() == before),
        check("document is complete", latex.strip().endswith("\\end{document}")),
        check("no placeholder survived", "{{" not in latex),
        check("output is pure ASCII", _is_ascii(latex)),
    ]

    leaked = [token for token in LEAKED_TOKENS if token in latex]
    results.append(
        check("no runtime metadata leaked {}".format(leaked or ""), not leaked)
    )

    path = renderer.render_to_file(resume)
    print("  wrote {}".format(path))

    if shutil.which("pdflatex"):
        results.append(check("pdflatex compiles the document", compile_document(latex)))
    else:
        print("  SKIP pdflatex is not installed, compilation unverified")

    return all(results)


def _is_ascii(text: str) -> bool:
    """True when the document contains no character pdflatex could mis-set."""
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def run_source_only(renderer: LatexRenderer) -> bool:
    """Render the three canonical resumes without touching a provider."""
    parser = ResumeParser()
    results = []
    for path in CANONICAL_RESUMES:
        results.append(verify(parser.parse(path), path, renderer))
    return all(results)


def run_generated(renderer: LatexRenderer, resume_path: str, jd_path: str, mode) -> bool:
    """Drive the full pipeline, then render what the generator produced."""
    config = ConfigManager().load()
    provider = ProviderFactory.create(config, CredentialManager())
    source = ResumeParser().parse(resume_path)
    job_description = Path(jd_path).read_text(encoding="utf-8").strip()
    print("model            {}".format(config.model))

    started = time.time()
    analysis = JDAnalyzer(provider).analyze(job_description)
    plan = ResumePlanner(provider).plan(
        resume=source, job_analysis=analysis, mode=mode
    )
    generated = ResumeGenerator(provider).generate(
        source_resume=source, job_analysis=analysis, resume_plan=plan, mode=mode
    )
    print("generated in {:.0f}s".format(time.time() - started))
    return verify(generated, "{} ({})".format(resume_path, mode.value), renderer)


def main() -> int:
    """Parse arguments, run the requested checks, and report overall status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="Render the canonical resumes without calling a provider",
    )
    parser.add_argument("--resume", help="Path to a Markdown resume")
    parser.add_argument("--jd", help="Path to a job description file")
    parser.add_argument("--mode", default="aggressive", help="strict or aggressive")
    parser.add_argument(
        "--templates", default="templates", help="Template directory to render from"
    )
    args = parser.parse_args()

    renderer = LatexRenderer(template_directory=args.templates)

    if args.source_only:
        passed = run_source_only(renderer)
    else:
        if not args.resume or not args.jd:
            parser.error("--resume and --jd are required unless --source-only is set")
        passed = run_generated(
            renderer, args.resume, args.jd, PlanningMode.parse(args.mode)
        )

    print()
    if passed:
        print("PASS: every rendered document passed its checks.")
        return 0
    print("FAIL: at least one check did not pass.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
