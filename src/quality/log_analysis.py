"""
Compiler-log parsing for Stage 1.

Page count, overfull hboxes and missing glyphs are all reported by the engine,
so reading the log is cheaper and more precise than inferring them from the
rendered page. Only the checks that genuinely need rendered geometry — overlap
and orphans — go to the PDF.

Logs are decoded with ``errors="replace"``: TeX writes file paths in the
filesystem's encoding and can emit bytes that are not valid UTF-8. Today's logs
happen to be pure ASCII, which is not a guarantee.
"""

import re
from typing import List, NamedTuple, Optional

# "Output written on resume.pdf (2 pages, 60711 bytes)." Absent when the engine
# produced no PDF, which is why the PDF is the primary source for page count.
PAGE_COUNT_RE = re.compile(r"Output written on \S+ \((\d+) pages?")

# "Overfull \hbox (12.34pt too wide) in paragraph at lines 42--43"
OVERFULL_RE = re.compile(r"Overfull \\hbox \(([\d.]+)pt too wide\)")

# "Missing character: There is no ^^c3 in font ..."
MISSING_GLYPH_RE = re.compile(r"Missing character: There is no (.+?) in font")


class LogFindings(NamedTuple):
    """Everything Stage 1 can learn from the compiler log."""

    page_count: Optional[int]
    overfull_points: List[float]
    missing_glyphs: List[str]


def read_log(log_path: str) -> str:
    """Read a compiler log, tolerating non-UTF-8 bytes."""
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def analyse_log(log_text: str) -> LogFindings:
    """Extract page count, overfull magnitudes and missing glyphs from a log."""
    page_match = PAGE_COUNT_RE.search(log_text)
    return LogFindings(
        page_count=int(page_match.group(1)) if page_match else None,
        overfull_points=[float(m) for m in OVERFULL_RE.findall(log_text)],
        missing_glyphs=MISSING_GLYPH_RE.findall(log_text),
    )
