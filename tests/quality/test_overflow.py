"""
Overflow magnitude and section attribution.

These metrics let the Revision Engine act on ``revision_order`` — "revise only
the affected sections" — instead of guessing. They are an accelerator rather
than a correctness requirement: at ~0.5s per compile the engine can also trim
one bullet and re-run.
"""

from src.quality.checks import attribute_sections, measure_overflow
from src.quality.models import REVISION_ORDER, ResumeSection

from .conftest import LINE_LEADING, make_line, make_page, make_rule


def section_page(headings, page_number=1, body_per_section=2):
    """A page of headings, each followed by its rule and some body lines."""
    lines, rules = [], []
    y = 750.0
    for heading in headings:
        lines.append(make_line(text=heading, baseline=y, page=page_number, width=70.0))
        rules.append(make_rule(baseline=y - 2.0, page=page_number))
        y -= LINE_LEADING
        for index in range(body_per_section):
            lines.append(
                make_line(
                    text="body line {0}".format(index), baseline=y, page=page_number
                )
            )
            y -= LINE_LEADING
    return make_page(lines, rules=rules, page_number=page_number)


class TestSectionAttribution:
    def test_body_lines_are_attributed_to_their_section(self):
        page = section_page(["SUMMARY", "PROJECTS"])
        mapping = attribute_sections([page])[1]
        assert ResumeSection.SUMMARY in mapping.values()
        assert ResumeSection.PROJECTS in mapping.values()

    def test_a_heading_belongs_to_its_own_section(self):
        # A heading sits *above* its own rule, so a naive marker walk files it
        # under the previous section.
        page = section_page(["SUMMARY", "PROJECTS"])
        heading = [line for line in page.lines if line.text == "PROJECTS"][0]
        assert attribute_sections([page])[1][heading.y0] is ResumeSection.PROJECTS

    def test_content_above_the_first_rule_is_unknown(self):
        # The contact block has no section.
        contact = make_line(text="Sundar S", baseline=780.0)
        page = section_page(["SUMMARY"])
        page.lines = [contact] + page.lines
        assert attribute_sections([page])[1][contact.y0] is ResumeSection.UNKNOWN

    def test_a_narrow_rule_is_not_a_section_boundary(self):
        # Link underlines are rects too; only full-width rules are titlerules.
        page = make_page([make_line(text="body", baseline=700.0)])
        page.rules = [make_rule(baseline=705.0)]
        page.rules[0].x1 = page.rules[0].x0 + 20.0
        assert attribute_sections([page])[1][700.0] is ResumeSection.UNKNOWN


class TestOverflow:
    def test_a_one_page_document_has_no_overflow(self):
        lines, _, sections, _ = measure_overflow([section_page(["SUMMARY"])])
        assert lines == 0 and sections == []

    def test_lines_on_page_two_are_counted(self):
        pages = [
            section_page(["SUMMARY"]),
            make_page(
                [make_line(page=2, baseline=700.0), make_line(page=2, baseline=686.0)],
                page_number=2,
            ),
        ]
        count, _, _, _ = measure_overflow(pages)
        assert count == 2

    def test_the_overflowing_section_is_named(self):
        second = section_page(["PROJECTS"], page_number=2)
        count, _, sections, _ = measure_overflow([section_page(["SUMMARY"]), second])
        assert ResumeSection.PROJECTS in sections

    def test_overflow_height_is_reported(self):
        pages = [
            section_page(["SUMMARY"]),
            make_page(
                [make_line(page=2, baseline=700.0), make_line(page=2, baseline=600.0)],
                page_number=2,
            ),
        ]
        _, height, _, _ = measure_overflow(pages)
        assert height > 0.0

    def test_lines_are_counted_per_section(self):
        _, _, _, per_section = measure_overflow([section_page(["SUMMARY", "PROJECTS"])])
        assert per_section[ResumeSection.SUMMARY] >= 2


class TestRevisionOrder:
    def test_it_matches_the_architecture_document(self):
        assert REVISION_ORDER[ResumeSection.SUMMARY] == 1
        assert REVISION_ORDER[ResumeSection.PROJECTS] == 2
        assert REVISION_ORDER[ResumeSection.SKILLS] == 3
        assert REVISION_ORDER[ResumeSection.EXPERIENCE] == 4

    def test_education_has_no_revision_order(self):
        # Education is immutable, so it is never a shortening target.
        assert ResumeSection.EDUCATION not in REVISION_ORDER
