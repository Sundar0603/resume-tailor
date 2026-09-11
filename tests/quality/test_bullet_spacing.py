"""
The bullet-spacing check.

The defect is a phantom empty line. When a bullet's last line fills the measure
exactly, a stray space token after it cannot fit, and TeX emits an extra line
one ``\\baselineskip`` tall carrying no glyphs. Nothing else in the gate can
see it: the compile log stays silent (``\\raggedright`` makes the line
non-overfull, ``\\raggedbottom`` suppresses the underfull vbox), and the
overlap check only looks for collisions. Only the distance between the two
bullets gives it away.

Measured, after the ``\\resumeItem`` fix: 115 sibling gaps across the nine
recompiled resumes, median 3.88, maximum 7.36 -- that maximum being the
structural project-title step. The defect measured 15.99 in four of the nine
before the fix and 14.57 / 14.62 in the two output/runs finals. The excess is
one leading, so the two populations cannot meet.
"""

import pytest

from src.quality.checks import BULLET_GAP_MAX_POINTS, find_bullet_spacing_anomalies

from .conftest import GLYPH_HEIGHT, LINE_LEADING, make_line, make_page

BULLET_X0 = 26.73
CONTINUATION_X0 = 36.0  # +9.27 from the bullet, as the compiled resumes show

# The gap the compiled resumes actually show between two single-line bullets,
# and the extra a phantom line adds.
SIBLING_GAP = 2.62
PHANTOM_LINE = 11.95


def bullet(text="a bullet of resume text", baseline=700.0, page=1, x0=BULLET_X0):
    """A bullet item's first line, carrying the glyph the check keys on."""
    return make_line(text="• " + text, baseline=baseline, page=page, x0=x0)


def continuation(text="wrapped remainder of the bullet", baseline=700.0, page=1):
    """A wrapped line belonging to the bullet above it."""
    return make_line(text=text, baseline=baseline, page=page, x0=CONTINUATION_X0)


def stacked(count, gap=SIBLING_GAP, top=700.0):
    """``count`` single-line bullets, each ``gap`` below the previous."""
    step = GLYPH_HEIGHT + gap
    return [bullet(text=f"bullet {i}", baseline=top - i * step) for i in range(count)]


class TestEvenlySpacedBullets:
    def test_a_normal_list_reports_nothing(self):
        assert find_bullet_spacing_anomalies([make_page(stacked(4))]) == []

    def test_a_single_bullet_has_no_gap_to_measure(self):
        assert find_bullet_spacing_anomalies([make_page(stacked(1))]) == []

    def test_an_empty_page_reports_nothing(self):
        assert find_bullet_spacing_anomalies([make_page([])]) == []

    def test_a_page_of_prose_reports_nothing(self):
        lines = [make_line(baseline=700.0 - i * LINE_LEADING) for i in range(4)]
        assert find_bullet_spacing_anomalies([make_page(lines)]) == []


class TestThePhantomLine:
    def test_an_extra_leading_between_siblings_is_reported(self):
        lines = stacked(4)
        for line in lines[2:]:
            line.y0 -= PHANTOM_LINE
            line.y1 -= PHANTOM_LINE
        found = find_bullet_spacing_anomalies([make_page(lines)])
        assert len(found) == 1

    def test_it_reports_the_two_bullets_it_sits_between(self):
        lines = stacked(4)
        for line in lines[2:]:
            line.y0 -= PHANTOM_LINE
            line.y1 -= PHANTOM_LINE
        preceding, following, _ = find_bullet_spacing_anomalies([make_page(lines)])[0]
        assert preceding.text.endswith("bullet 1")
        assert following.text.endswith("bullet 2")

    def test_the_magnitude_is_the_measured_gap(self):
        lines = stacked(4)
        for line in lines[2:]:
            line.y0 -= PHANTOM_LINE
            line.y1 -= PHANTOM_LINE
        _, _, gap = find_bullet_spacing_anomalies([make_page(lines)])[0]
        assert gap == pytest.approx(SIBLING_GAP + PHANTOM_LINE)

    def test_it_is_found_on_any_page(self):
        lines = stacked(3, top=400.0)
        for line in lines[1:]:
            line.y0 -= PHANTOM_LINE
            line.y1 -= PHANTOM_LINE
        for line in lines:
            line.page = 2
        found = find_bullet_spacing_anomalies([make_page(lines, page_number=2)])
        assert len(found) == 1


class TestWrappedBullets:
    def test_the_gap_is_measured_from_the_last_line_not_the_first(self):
        # A two-line bullet followed by a normally-spaced sibling. Measuring
        # from the bullet's first line would see a whole extra leading and
        # report a defect that is not there.
        first = bullet(baseline=700.0)
        wrapped = continuation(baseline=700.0 - LINE_LEADING)
        following = bullet(
            text="next", baseline=700.0 - LINE_LEADING - GLYPH_HEIGHT - SIBLING_GAP
        )
        page = make_page([first, wrapped, following])
        assert find_bullet_spacing_anomalies([page]) == []

    def test_a_phantom_line_after_a_wrapped_bullet_is_still_caught(self):
        first = bullet(baseline=700.0)
        wrapped = continuation(baseline=700.0 - LINE_LEADING)
        base = 700.0 - LINE_LEADING - GLYPH_HEIGHT - SIBLING_GAP
        following = bullet(text="next", baseline=base - PHANTOM_LINE)
        page = make_page([first, wrapped, following])
        assert len(find_bullet_spacing_anomalies([page])) == 1


class TestStructuralGapsAreNotDefects:
    def test_a_project_title_and_its_first_sub_bullet_are_not_compared(self):
        # The title sits at the outer indent, its bullets one step in. The
        # 7.36pt step between them is in every compiled resume.
        title = bullet(text="Secure CI/CD Pipeline", baseline=700.0)
        child = bullet(
            text="first highlight",
            baseline=700.0 - GLYPH_HEIGHT - 7.36,
            x0=BULLET_X0 + 7.2,
        )
        assert find_bullet_spacing_anomalies([make_page([title, child])]) == []

    def test_a_heading_between_two_lists_breaks_the_run(self):
        above = stacked(2, top=700.0)
        heading = make_line(text="PROJECTS", baseline=600.0, x0=29.1)
        below = stacked(2, top=500.0)
        page = make_page(above + [heading] + below)
        assert find_bullet_spacing_anomalies([page]) == []

    def test_bullets_separated_by_a_heading_are_never_paired(self):
        # The large distance across the heading must not be reported even
        # though both sides are bullets at the same indent.
        page = make_page(
            [
                bullet(text="last of section", baseline=700.0),
                make_line(text="PROJECTS", baseline=650.0, x0=29.1),
                bullet(text="first of section", baseline=600.0),
            ]
        )
        assert find_bullet_spacing_anomalies([page]) == []


class TestTheThreshold:
    def test_the_threshold_clears_the_structural_step(self):
        # 7.36 is the largest legitimate gap in the corpus.
        assert BULLET_GAP_MAX_POINTS > 7.36

    def test_the_threshold_sits_below_the_smallest_real_defect(self):
        # 14.57 is the smallest phantom-line gap measured.
        assert BULLET_GAP_MAX_POINTS < 14.57

    def test_a_gap_exactly_at_the_threshold_is_not_reported(self):
        lines = stacked(2)
        lines[1].y0 = lines[0].y0 - GLYPH_HEIGHT - BULLET_GAP_MAX_POINTS
        lines[1].y1 = lines[1].y0 + GLYPH_HEIGHT
        assert find_bullet_spacing_anomalies([make_page(lines)]) == []
