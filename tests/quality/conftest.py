"""
Shared factories for the Quality Gate tests.

Plain factory functions and hand-written fakes, matching the compiler, renderer
and generator suites. The gate takes an ``extractor`` callable precisely so
these tests can drive every Stage 2 branch without a PDF, without pdflatex and
without pdfminer — the same reason the Compiler takes a ``runner``.

Geometry here is built in PDF user-space: y increases upward, so a *lower* line
on the page has a *smaller* y. The builders take a baseline and a height and
work that out, because getting it backwards silently inverts every overlap test.
"""

from typing import List, Optional

from src.compiler.models import CompilationResult
from src.quality.geometry import PageGeometry, Rule, TextLine

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

# The frozen templates' text column, measured from the compiled resumes.
COLUMN_X0 = 28.8
COLUMN_X1 = 582.5
COLUMN_WIDTH = COLUMN_X1 - COLUMN_X0

# Body-text leading in the compiled resumes.
LINE_LEADING = 13.55
GLYPH_HEIGHT = 10.9


def make_line(
    text: str = "a bullet of resume text",
    baseline: float = 700.0,
    page: int = 1,
    x0: float = COLUMN_X0,
    width: Optional[float] = None,
    height: float = GLYPH_HEIGHT,
) -> TextLine:
    """One row of text at a given baseline, filling the column by default."""
    span = COLUMN_WIDTH if width is None else width
    return TextLine(
        page=page,
        text=text,
        x0=x0,
        y0=baseline,
        x1=x0 + span,
        y1=baseline + height,
        baseline=baseline,
        font_size=height,
    )


def make_page(
    lines: Optional[List[TextLine]] = None,
    raw_rows: Optional[List[TextLine]] = None,
    rules: Optional[List[Rule]] = None,
    page_number: int = 1,
) -> PageGeometry:
    """A page. ``raw_rows`` defaults to ``lines`` when not given separately."""
    resolved = [] if lines is None else lines
    return PageGeometry(
        page_number=page_number,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        lines=resolved,
        raw_rows=resolved if raw_rows is None else raw_rows,
        rules=[] if rules is None else rules,
    )


def make_rule(baseline: float = 717.6, page: int = 1) -> Rule:
    """A full-width section rule, as ``\\titlerule`` draws it."""
    return Rule(page=page, x0=COLUMN_X0, y0=baseline, x1=COLUMN_X1, y1=baseline)


def make_paragraph(
    texts: List[str],
    top: float = 700.0,
    page: int = 1,
    x0: float = COLUMN_X0,
    fills: Optional[List[float]] = None,
) -> List[TextLine]:
    """
    A wrapped block: consecutive lines at one indent, one leading apart.

    ``fills`` gives each line's share of the column width, so a test can say
    "this line wrapped full" (0.95) or "this line stopped early" (0.4).
    """
    ratios = fills if fills is not None else [0.95] * len(texts)
    return [
        make_line(
            text=text,
            baseline=top - index * LINE_LEADING,
            page=page,
            x0=x0,
            width=COLUMN_WIDTH * ratio,
        )
        for index, (text, ratio) in enumerate(zip(texts, ratios))
    ]


class FakeExtractor:
    """
    Returns canned geometry and records what it was asked for.

    Mirrors ``FakeRunner`` in the compiler suite: a hand-written stand-in for
    the seam, not a mocking-library patch.
    """

    def __init__(self, pages: Optional[List[PageGeometry]] = None) -> None:
        self.pages = [make_page()] if pages is None else pages
        self.calls: List[str] = []

    def __call__(self, pdf_path: str) -> List[PageGeometry]:
        self.calls.append(pdf_path)
        return self.pages


class FailingExtractor:
    """Raises whatever it was given, to prove errors are never swallowed."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __call__(self, pdf_path: str) -> List[PageGeometry]:
        raise self.error


def make_log(
    pages: Optional[int] = 1,
    overfull: Optional[List[float]] = None,
    missing_glyphs: Optional[List[str]] = None,
) -> str:
    """A compiler log carrying exactly the diagnostics a test cares about."""
    parts = ["This is pdfTeX, Version 3.141592653", "(./resume.tex"]
    for width in overfull or []:
        parts.append(
            "Overfull \\hbox ({0}pt too wide) in paragraph at lines 10--11".format(width)
        )
    for glyph in missing_glyphs or []:
        parts.append(
            "Missing character: There is no {0} in font ptmr8r!".format(glyph)
        )
    if pages is not None:
        parts.append(
            "Output written on resume.pdf ({0} page{1}, 60711 bytes).".format(
                pages, "" if pages == 1 else "s"
            )
        )
    parts.append("Transcript written on resume.log.")
    return "\n".join(parts) + "\n"


def write_log(tmp_path, text: str) -> str:
    """Write a log to disk and return its path."""
    path = tmp_path / "resume.log"
    path.write_text(text, encoding="utf-8")
    return str(path)


def make_compilation_result(log_path: str, **overrides) -> CompilationResult:
    """A successful CompilationResult pointing at a real log file."""
    values = dict(
        pdf_path="resume.pdf",
        log_path=log_path,
        tex_path="resume.tex",
        engine="/usr/bin/pdflatex",
        exit_code=0,
        duration_seconds=0.5,
    )
    values.update(overrides)
    return CompilationResult(**values)
