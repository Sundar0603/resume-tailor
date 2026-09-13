"""
The bottom-margin rule.

``measure_overflow`` only ever counted lines on page two and later, so content
that ran off the bottom of page *one* was invisible: LaTeX reports no Overfull
\\vbox for it (``\\raggedbottom`` plus the template's negative struts), and the
gate recorded ``passed: true, spill: 0`` for a resume whose last bullet was
sliced through the glyphs. These pin the rule that closes that gap.
"""

import pytest

from src.quality.checks import MIN_BOTTOM_MARGIN_POINTS, bottom_margin
from src.quality.models import QualityIssueCode

from src.quality import QualityGate

from .conftest import (
    FakeExtractor,
    make_compilation_result,
    make_line,
    make_log,
    make_page,
    make_rule,
    write_log,
)


def evaluate(tmp_path, pages):
    path = write_log(tmp_path, make_log(pages=1))
    gate = QualityGate(extractor=FakeExtractor(pages))
    return gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))


class TestTheMarginMeasurement:
    def test_it_is_the_lowest_line_on_the_last_page(self):
        page = make_page([make_line(baseline=700.0), make_line(baseline=120.0)])
        assert bottom_margin([page]) == pytest.approx(120.0)

    def test_a_rule_below_the_last_line_counts(self):
        # A section rule sitting under the final line is cut just as the text
        # would be, so it has to be part of the measurement.
        page = make_page([make_line(baseline=200.0)], rules=[make_rule(baseline=40.0)])
        assert bottom_margin([page]) == pytest.approx(40.0)

    def test_only_the_final_page_is_measured(self):
        # Page one always ends near the bottom -- that is what a full page is.
        full = make_page([make_line(baseline=2.0)], page_number=1)
        short = make_page([make_line(baseline=600.0)], page_number=2)
        assert bottom_margin([full, short]) == pytest.approx(600.0)

    def test_an_empty_page_is_not_too_full(self):
        assert bottom_margin([make_page([])]) > MIN_BOTTOM_MARGIN_POINTS

    def test_no_pages_at_all(self):
        assert bottom_margin([]) == 0.0


class TestTheRuleBlocks:
    """ERROR, not a warning: a cut line is not a cosmetic imperfection."""

    def _codes(self, gate_result):
        return [i.code for i in gate_result.issues]

    def test_content_at_the_very_edge_is_flagged(self, tmp_path):
        result = evaluate(tmp_path, [make_page([make_line(baseline=0.0)])])
        assert QualityIssueCode.CONTENT_BELOW_BOTTOM_MARGIN in self._codes(result)
        assert result.passed is False

    def test_a_healthy_margin_passes(self, tmp_path):
        result = evaluate(
            tmp_path,
            [make_page([make_line(baseline=MIN_BOTTOM_MARGIN_POINTS + 10.0)])]
        )
        assert QualityIssueCode.CONTENT_BELOW_BOTTOM_MARGIN not in self._codes(result)

    def test_the_boundary_itself_is_allowed(self, tmp_path):
        result = evaluate(
            tmp_path,
            [make_page([make_line(baseline=MIN_BOTTOM_MARGIN_POINTS)])]
        )
        assert QualityIssueCode.CONTENT_BELOW_BOTTOM_MARGIN not in self._codes(result)
