"""Stage 1 log parsing: page count, overfull hboxes, missing glyphs."""

from src.quality.log_analysis import analyse_log, read_log

from .conftest import make_log, write_log


class TestPageCount:
    def test_it_reads_a_single_page(self):
        assert analyse_log(make_log(pages=1)).page_count == 1

    def test_it_reads_a_multi_page_document(self):
        assert analyse_log(make_log(pages=2)).page_count == 2

    def test_a_log_without_an_output_line_reports_no_page_count(self):
        assert analyse_log(make_log(pages=None)).page_count is None


class TestOverfullHboxes:
    def test_a_clean_log_has_none(self):
        assert analyse_log(make_log()).overfull_points == []

    def test_it_captures_a_single_magnitude(self):
        assert analyse_log(make_log(overfull=[12.34])).overfull_points == [12.34]

    def test_it_captures_every_magnitude(self):
        findings = analyse_log(make_log(overfull=[0.5, 20.0, 3.25]))
        assert findings.overfull_points == [0.5, 20.0, 3.25]

    def test_the_magnitude_is_what_distinguishes_a_hairline_from_an_intrusion(self):
        # 0.5pt is invisible; 20pt runs into the margin. The count alone cannot
        # tell them apart, which is why the width travels with the finding.
        findings = analyse_log(make_log(overfull=[0.5, 20.0]))
        assert max(findings.overfull_points) == 20.0


class TestMissingGlyphs:
    def test_a_clean_log_has_none(self):
        assert analyse_log(make_log()).missing_glyphs == []

    def test_it_captures_one(self):
        assert len(analyse_log(make_log(missing_glyphs=["^^c3"])).missing_glyphs) == 1

    def test_it_captures_several(self):
        findings = analyse_log(make_log(missing_glyphs=["^^c3", "^^a9", "^^e2"]))
        assert len(findings.missing_glyphs) == 3


class TestReadingFromDisk:
    def test_it_reads_a_log_file(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=2))
        assert analyse_log(read_log(path)).page_count == 2

    def test_it_tolerates_bytes_that_are_not_utf8(self, tmp_path):
        # TeX writes paths in the filesystem encoding and can emit invalid
        # UTF-8. Today's logs are pure ASCII; that is not a guarantee.
        path = tmp_path / "resume.log"
        path.write_bytes(b"Output written on resume.pdf (1 page).\n\xff\xfe bad\n")
        assert analyse_log(read_log(str(path))).page_count == 1
