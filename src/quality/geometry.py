"""
PDF geometry extraction — the only module that imports pdfminer.

Everything downstream operates on :class:`PageGeometry`, which is why the
Stage 2 rules are testable with pdfminer absent: a fake extractor returns
hand-built pages and the rules never know the difference. Same idea as the
Compiler's ``runner`` seam.

**Two passes, deliberately.** The two checks need opposite things from the
same document:

- The *analysed* pass (``extract_pages`` with default ``LAParams``) groups
  glyphs into lines and reinstates spaces. Orphan detection, section
  attribution and overflow counting need that.
- The *raw* pass (``PDFPageAggregator(laparams=None)``) does no layout
  analysis at all. Overlap detection needs that, because layout analysis is
  precisely what *hides* superimposed text: two colliding bullets get merged
  into one line and their boxes then never intersect. Measured on the
  regression fixture: the analysed pass loses the collisions entirely.

Note ``extract_pages(..., laparams=None)`` does **not** give a raw pass —
``pdfminer/high_level.py`` substitutes a default ``LAParams()`` when it is
``None``. The aggregator has to be driven directly.

Baselines come from ``LTChar.matrix[5]``, the glyph origin, which is the only
font-size independent baseline available. It is undocumented pdfminer API, so
``tests/quality/test_geometry.py`` pins the known-good line leading; an upgrade
that changes the semantics fails loudly instead of silently splitting every
line into its own row and disabling overlap detection.
"""

import logging
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .exceptions import GeometryUnavailableError, PDFUnreadableError

try:  # pragma: no cover - exercised by the import-failure test
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTLine, LTRect, LTTextLine
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    PDFMINER_AVAILABLE = True
except ImportError:  # pragma: no cover
    PDFMINER_AVAILABLE = False


# pdfminer logs "CropBox missing from /Page" at WARNING for every page. Silence
# its own logger; never touch the root logger from library code.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# Baselines within this many points are the same visual row.
BASELINE_TOLERANCE_POINTS = 1.0


class TextLine(BaseModel):
    """One row of text, with the geometry the rules need."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    page: int = Field(ge=1)
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    font_size: float = Field(ge=0.0)

    @property
    def width(self) -> float:
        """Horizontal extent in points."""
        return self.x1 - self.x0

    @property
    def word_count(self) -> int:
        """Whitespace-separated tokens."""
        return len(self.text.split())


class Rule(BaseModel):
    """A drawn horizontal rule. One per section heading, from ``\\titlerule``."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    page: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float


class PageGeometry(BaseModel):
    """
    One page, from both passes.

    ``lines`` is the analysed pass (real spaces, layout grouping); ``raw_rows``
    is the unanalysed pass (no spaces, one entry per glyph baseline).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    page_number: int = Field(ge=1)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)
    lines: List[TextLine] = Field(default_factory=list)
    raw_rows: List[TextLine] = Field(default_factory=list)
    rules: List[Rule] = Field(default_factory=list)


def _collect(container, wanted) -> List:
    """Depth-first walk of a pdfminer layout tree, gathering instances."""
    found = []
    stack = [container]
    while stack:
        node = stack.pop()
        for element in node:
            if isinstance(element, wanted):
                found.append(element)
            elif hasattr(element, "__iter__"):
                stack.append(element)
    return found


def _group_by_baseline(chars: List, page_number: int) -> List[TextLine]:
    """
    Cluster glyphs into rows by ``matrix[5]``.

    Raw glyphs carry no spaces — TeX kerns via ``TJ`` rather than emitting
    space characters — so the text here reads ``TECHNICALSKILLS``. Callers that
    compare it to a heading must strip whitespace from both sides of the
    comparison.
    """
    buckets = {}
    for char in chars:
        baseline = round(char.matrix[5], 1)
        key = None
        for existing in buckets:
            if abs(existing - baseline) <= BASELINE_TOLERANCE_POINTS:
                key = existing
                break
        buckets.setdefault(baseline if key is None else key, []).append(char)

    rows = []
    for baseline, glyphs in buckets.items():
        ordered = sorted(glyphs, key=lambda c: c.x0)
        rows.append(
            TextLine(
                page=page_number,
                text="".join(c.get_text() for c in ordered),
                x0=min(c.x0 for c in glyphs),
                y0=min(c.y0 for c in glyphs),
                x1=max(c.x1 for c in glyphs),
                y1=max(c.y1 for c in glyphs),
                baseline=baseline,
                font_size=max(c.size for c in glyphs),
            )
        )
    return sorted(rows, key=lambda r: -r.baseline)


def _raw_pages(pdf_path: str) -> List[List[TextLine]]:
    """Drive the aggregator with layout analysis switched off."""
    manager = PDFResourceManager()
    device = PDFPageAggregator(manager, laparams=None)
    interpreter = PDFPageInterpreter(manager, device)
    pages = []
    with open(pdf_path, "rb") as handle:
        for number, page in enumerate(PDFPage.get_pages(handle), start=1):
            interpreter.process_page(page)
            layout = device.get_result()
            pages.append(_group_by_baseline(_collect(layout, LTChar), number))
    return pages


def pdfminer_extractor(pdf_path: str) -> List[PageGeometry]:
    """
    Read a PDF into :class:`PageGeometry`, one entry per page.

    Raises
    ------
    GeometryUnavailableError
        pdfminer is not installed.
    PDFUnreadableError
        The file is missing, is not a PDF, has no pages, or cannot be parsed.
    """
    if not PDFMINER_AVAILABLE:
        raise GeometryUnavailableError(
            "pdfminer.six is required for PDF geometry analysis. "
            "Install it with: pip install 'pdfminer.six>=20231228,<20251227'"
        )

    try:
        raw = _raw_pages(pdf_path)
        pages = []
        for number, page in enumerate(extract_pages(pdf_path), start=1):
            lines = [
                TextLine(
                    page=number,
                    text=element.get_text().rstrip("\n"),
                    x0=element.x0,
                    y0=element.y0,
                    x1=element.x1,
                    y1=element.y1,
                    baseline=element.y0,
                    font_size=element.height,
                )
                for element in _collect(page, LTTextLine)
            ]
            rules = [
                Rule(page=number, x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)
                for r in _collect(page, (LTRect, LTLine))
            ]
            pages.append(
                PageGeometry(
                    page_number=number,
                    width=page.width,
                    height=page.height,
                    lines=sorted(lines, key=lambda line: -line.y0),
                    raw_rows=raw[number - 1] if number <= len(raw) else [],
                    rules=rules,
                )
            )
    except (GeometryUnavailableError, PDFUnreadableError):
        raise
    except Exception as error:
        raise PDFUnreadableError(
            "Could not analyse the PDF at {0}: {1}".format(pdf_path, error)
        )

    if not pages:
        raise PDFUnreadableError(
            "The PDF at {0} contains no pages. The Compiler accepts a file "
            "with valid magic bytes and no content; judging it is this "
            "package's job.".format(pdf_path)
        )
    return pages
