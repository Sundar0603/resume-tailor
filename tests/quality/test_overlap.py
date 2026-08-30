"""
Text-overlap detection.

The regression this exists for (§10d): per-bullet negative vspace made
consecutive bullets print on top of each other. pdflatex exited 0 with no
warnings, brace balance was fine, and the page count *improved* — because the
text was collapsing onto itself rather than fitting. Page count is a
compression measure, and overlap is infinite compression.
"""

from src.quality.checks import OVERLAP_TOLERANCE_POINTS, find_overlaps

from .conftest import COLUMN_X0, COLUMN_WIDTH, GLYPH_HEIGHT, make_line, make_page


class TestCleanLayout:
    def test_normally_spaced_lines_do_not_overlap(self):
        page = make_page(
            [make_line(baseline=700.0), make_line(baseline=686.45)]
        )
        assert find_overlaps([page]) == []

    def test_a_single_line_cannot_overlap(self):
        assert find_overlaps([make_page([make_line()])]) == []

    def test_an_empty_page_cannot_overlap(self):
        assert find_overlaps([make_page([])]) == []

    def test_lines_that_merely_touch_do_not_overlap(self):
        # Adjacent baselines exactly one glyph height apart: the boxes abut but
        # no ink collides.
        page = make_page(
            [make_line(baseline=700.0), make_line(baseline=700.0 - GLYPH_HEIGHT)]
        )
        assert find_overlaps([page]) == []


class TestLegitimateAdjacentText:
    def test_a_right_aligned_date_beside_a_company_is_not_an_overlap(self):
        # \resumeSubheading puts company and date in one tabular row: same
        # baseline, horizontally disjoint. Requiring intersection on *both*
        # axes is what keeps this from registering.
        page = make_page(
            [
                make_line(text="Zoho Corporation", baseline=700.0, width=120.0),
                make_line(
                    text="2023 - 2025",
                    baseline=700.0,
                    x0=COLUMN_X0 + 450.0,
                    width=70.0,
                ),
            ]
        )
        assert find_overlaps([page]) == []

    def test_tight_but_disjoint_columns_do_not_overlap(self):
        page = make_page(
            [
                make_line(text="left", baseline=700.0, width=100.0),
                make_line(text="right", baseline=698.0, x0=COLUMN_X0 + 200.0, width=80.0),
            ]
        )
        assert find_overlaps([page]) == []


class TestGenuineOverlap:
    def test_colliding_lines_are_reported(self):
        # 4pt apart with ~11pt glyphs: the ink genuinely collides.
        page = make_page(
            [make_line(baseline=700.0), make_line(baseline=696.0)]
        )
        found = find_overlaps([page])
        assert len(found) == 1

    def test_the_magnitude_is_reported(self):
        page = make_page(
            [make_line(baseline=700.0), make_line(baseline=696.0)]
        )
        _, _, ink = find_overlaps([page])[0]
        assert abs(ink - (696.0 + GLYPH_HEIGHT - 700.0)) < 0.01

    def test_overlap_is_detected_from_raw_rows_not_analysed_lines(self):
        # Layout analysis merges colliding rows into one line, which is exactly
        # how the collision disappears. The check must read the raw pass.
        colliding = [make_line(baseline=700.0), make_line(baseline=696.0)]
        merged = [make_line(text="both bullets merged", baseline=700.0)]
        page = make_page(lines=merged, raw_rows=colliding)
        assert len(find_overlaps([page])) == 1

    def test_overlap_is_found_on_any_page(self):
        page = make_page(
            [make_line(baseline=700.0, page=2), make_line(baseline=696.0, page=2)],
            page_number=2,
        )
        assert len(find_overlaps([page])) == 1


class TestTheTolerance:
    def test_the_default_sits_below_the_smallest_measured_collision(self):
        # Calibrated: the nine known-good resumes produce zero overlapping
        # pairs; the regression fixture produces collisions from 1.79pt up.
        # Any value in (0, 1.79) separates them.
        assert 0.0 < OVERLAP_TOLERANCE_POINTS < 1.79
