"""
Orphan-word detection.

A "runt": a single word left alone on the last line of a wrapped block. Not the
typographic orphan/widow, which is a stranded *line* at a page boundary; the
task doc's name is kept and the docstrings say what is actually measured.
"""

from src.quality.checks import (
    ORPHAN_MAX_WORDS,
    ORPHAN_PRECEDING_FILL_RATIO,
    find_orphans,
)

from .conftest import COLUMN_X0, make_line, make_page, make_paragraph, make_rule


class TestNoOrphans:
    def test_a_block_ending_in_a_full_line_has_none(self):
        page = make_page(make_paragraph(["first line wraps here", "second full line"]), rules=[make_rule()])
        assert find_orphans([page]) == []

    def test_a_single_line_block_is_never_an_orphan(self):
        # One line cannot be a stranded remainder — there is nothing it wrapped
        # from.
        assert find_orphans([make_page([make_line(text="alone", width=40.0)], rules=[make_rule()])]) == []

    def test_an_empty_page_has_none(self):
        assert find_orphans([make_page([], rules=[make_rule()])]) == []


class TestGenuineOrphans:
    def test_one_word_after_a_full_line_is_an_orphan(self):
        page = make_page(
            make_paragraph(
                ["Implemented a scalable distributed processing architecture", "systems."],
                fills=[0.95, 0.06],
            ),
            rules=[make_rule()],
        )
        found = find_orphans([page])
        assert len(found) == 1
        assert found[0].text.strip() == "systems."

    def test_several_orphans_are_all_reported(self):
        lines = make_paragraph(
            ["a long line that wrapped across the column", "validation."],
            top=700.0,
            fills=[0.95, 0.06],
        )
        lines += make_paragraph(
            ["another long line that also wrapped fully", "integrations."],
            top=600.0,
            fills=[0.93, 0.08],
        )
        assert len(find_orphans([make_page(lines, rules=[make_rule()])])) == 2


class TestExclusions:
    def test_a_short_last_line_after_a_short_line_is_not_an_orphan(self):
        # The preceding line did not fill the column, so nothing wrapped — this
        # is an ordinary short block, not a runt.
        page = make_page(
            make_paragraph(["short line", "word"], fills=[0.40, 0.06]),
            rules=[make_rule()],
        )
        assert find_orphans([page]) == []

    def test_a_two_word_last_line_is_not_an_orphan_by_default(self):
        # 'Databases: MySQL' is a real skills line in the corpus at fill 0.978.
        # The word-count test is what rejects it.
        page = make_page(
            make_paragraph(
                ["Programming: Java, Python, Go and friends", "Databases: MySQL"],
                fills=[0.97, 0.20],
            ),
            rules=[make_rule()],
        )
        assert find_orphans([page]) == []

    def test_a_section_heading_is_never_an_orphan(self):
        page = make_page(
            make_paragraph(
                ["a full line of body text that wrapped", "PROJECTS"],
                fills=[0.95, 0.10],
            ),
            rules=[make_rule()],
        )
        assert find_orphans([page]) == []


class TestTheThresholds:
    def test_only_a_single_word_counts_by_default(self):
        assert ORPHAN_MAX_WORDS == 1

    def test_the_fill_guard_sits_below_every_measured_orphan(self):
        # Measured across the nine compiled resumes: five genuine orphans, all
        # with a preceding-line fill between 0.904 and 0.932.
        assert ORPHAN_PRECEDING_FILL_RATIO < 0.904
