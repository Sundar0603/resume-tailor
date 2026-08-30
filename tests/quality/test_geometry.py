"""
Geometry extraction against real PDFs.

Skipped when the compiled corpus is absent (``output/`` is gitignored), so the
suite still runs on a clean checkout.
"""

import os

import pytest

from src.quality.geometry import BASELINE_TOLERANCE_POINTS, pdfminer_extractor

CORPUS = "output/compile/backend_strict/backend_strict.pdf"

pytestmark = pytest.mark.skipif(
    not os.path.exists(CORPUS),
    reason="the compiled corpus under output/ is not present",
)

# Body-text leading measured in the compiled resumes.
EXPECTED_LEADING_POINTS = 13.55


class TestExtraction:
    def test_it_reads_every_page(self):
        assert len(pdfminer_extractor(CORPUS)) == 2

    def test_pages_carry_analysed_lines(self):
        assert len(pdfminer_extractor(CORPUS)[0].lines) > 0

    def test_pages_carry_raw_rows(self):
        assert len(pdfminer_extractor(CORPUS)[0].raw_rows) > 0

    def test_section_rules_are_kept(self):
        # A titlerule is a vector element. Discarding rects would hide a rule
        # drawn through text.
        assert len(pdfminer_extractor(CORPUS)[0].rules) > 0

    def test_the_page_is_letter_sized(self):
        page = pdfminer_extractor(CORPUS)[0]
        assert round(page.width) == 612 and round(page.height) == 792


class TestBaselineSemantics:
    def test_the_measured_leading_matches_the_template(self):
        # LTChar.matrix[5] is undocumented pdfminer API and is the only
        # font-size independent baseline available. If an upgrade changes its
        # semantics, every line splits into its own row and overlap detection
        # silently stops working. This pins it so the break is loud.
        rows = pdfminer_extractor(CORPUS)[0].raw_rows
        baselines = sorted({row.baseline for row in rows}, reverse=True)
        gaps = [
            round(a - b, 2)
            for a, b in zip(baselines, baselines[1:])
            if abs((a - b) - EXPECTED_LEADING_POINTS) < 1.0
        ]
        assert gaps, "no body-text leading near {0}pt found".format(
            EXPECTED_LEADING_POINTS
        )

    def test_the_clustering_tolerance_is_below_the_leading(self):
        # A tolerance at or above the leading would merge separate lines.
        assert BASELINE_TOLERANCE_POINTS < EXPECTED_LEADING_POINTS
