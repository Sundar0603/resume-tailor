"""
The rendered document actually compiles.

Everything else in the LaTeX suite is structural: brace balance, placeholder
substitution, ASCII-only output. Those are proxies. This file is the real
check: compiling is the only thing that proves the output is LaTeX at all.

It is not, however, sufficient. A document whose bullets overlap compiles
cleanly, reports no warnings, and comes out *shorter*. See
``test_latex_overlap.py`` for the structural guard that catches that, and look
at a rendered PDF before trusting any page count.

Skipped when pdflatex is not installed, so the suite still runs anywhere. Set
up the toolchain with TinyTeX plus the packages listed in PROJECT_KNOWLEDGE
§10d.
"""

import re
import shutil
from pathlib import Path

import pytest

from src.compiler import CompilationFailedError, PDFCompiler
from src.parser import ResumeParser
from src.renderer import LatexRenderer

from .conftest import CANONICAL_RESUMES, make_resume, make_sparse_resume

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)

PAGE_COUNT = re.compile(r"Output written on \S+ \((\d+) page")


def compile_latex(latex, tmp_path):
    """
    Compile a document and return (page_count, log). page_count is 0 on failure.

    Delegates to the PDF Compiler rather than shelling out here. The log is now
    TeX's own transcript instead of captured stdout — a superset, and the only
    place a "Missing character" warning is guaranteed to appear.
    """
    try:
        result = PDFCompiler().compile(latex, output_directory=str(tmp_path))
    except CompilationFailedError as failure:
        return 0, _read_log(failure.log_path)
    log = _read_log(result.log_path)
    match = PAGE_COUNT.search(log)
    return (int(match.group(1)) if match else -1), log


def _read_log(path):
    """Read a compiler log, tolerating the non-UTF-8 bytes TeX sometimes emits."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


class TestCompiles:
    def test_a_full_resume_compiles(self, tmp_path):
        pages, log = compile_latex(LatexRenderer().render(make_resume()), tmp_path)
        assert pages > 0, log[-3000:]

    def test_a_sparse_resume_compiles(self, tmp_path):
        pages, log = compile_latex(
            LatexRenderer().render(make_sparse_resume()), tmp_path
        )
        assert pages > 0, log[-3000:]

    def test_every_canonical_resume_compiles(self, tmp_path):
        # Deliberately NOT asserting one page. The masters reach one page by
        # hand-tuned per-bullet negative vspace; the renderer does not invent
        # that, so honest output runs to two pages and fitting is the Quality
        # Gate's job. An earlier version of this test asserted pages == 1 and
        # passed on a document whose bullets were overlapping — the assertion
        # was satisfiable by destroying the layout, which is worse than no
        # assertion at all.
        for index, path in enumerate(CANONICAL_RESUMES):
            resume = ResumeParser().parse(path)
            directory = tmp_path / str(index)
            directory.mkdir()
            pages, log = compile_latex(LatexRenderer().render(resume), directory)
            assert pages > 0, "{} failed to compile\n{}".format(path, log[-3000:])

    def test_every_template_compiles(self, tmp_path):
        for index, name in enumerate(["backend", "fullstack", "cybersecurity"]):
            resume = make_resume()
            resume.metadata.template = name
            directory = tmp_path / name
            directory.mkdir()
            pages, log = compile_latex(LatexRenderer().render(resume), directory)
            assert pages > 0, "{}: {}".format(name, log[-3000:])


class TestEscapedContentCompiles:
    def test_every_special_character_compiles(self, tmp_path):
        resume = make_resume()
        resume.summary = (
            "Handled 100% of R&D costs under $5 budgets, using C# and "
            "file_names with {braces}, ~tildes, ^carets and \\backslashes, "
            "plus a #hashtag."
        )
        pages, log = compile_latex(LatexRenderer().render(resume), tmp_path)
        assert pages > 0, log[-3000:]

    def test_transliterated_punctuation_compiles(self, tmp_path):
        resume = make_resume()
        resume.experiences[0].highlights = [
            "Cut latency 2019–2024 — the team’s “best” "
            "result … and counting",
        ]
        pages, log = compile_latex(LatexRenderer().render(resume), tmp_path)
        assert pages > 0, log[-3000:]

    def test_urls_with_specials_compile(self, tmp_path):
        resume = make_resume()
        resume.projects[0].repository = "https://example.com/a_b?x=1&y=2#frag"
        resume.contact.linkedin = "https://linkedin.com/in/me_name?trk=nav"
        pages, log = compile_latex(LatexRenderer().render(resume), tmp_path)
        assert pages > 0, log[-3000:]

    def test_no_missing_character_warnings(self, tmp_path):
        # A glyph the font lacks is dropped silently in the PDF, so the warning
        # is the only signal that content was lost.
        resume = ResumeParser().parse(CANONICAL_RESUMES[0])
        pages, log = compile_latex(LatexRenderer().render(resume), tmp_path)
        assert pages > 0, log[-3000:]
        assert "Missing character" not in log
