"""
Severity: which findings block submission and which are only reported.

Mirrors the Validator's errors-vs-warnings split. The gate previously treated
every finding as blocking, which failed a resume that was correct in every
respect except that one bullet ended with a single word on its own line.
"""

from src.quality import (
    QualityGate,
    QualityIssueCode,
    QualitySeverity,
    SEVERITY_BY_CODE,
)

from .conftest import (
    FakeExtractor,
    make_compilation_result,
    make_line,
    make_log,
    make_page,
    make_paragraph,
    make_rule,
    write_log,
)


def orphan_page():
    """One page whose only flaw is a stranded final word."""
    return make_page(
        make_paragraph(
            ["Implemented a scalable distributed processing architecture", "systems."],
            fills=[0.95, 0.06],
        ),
        rules=[make_rule()],
    )


def evaluate(tmp_path, pages, log_text=None):
    path = write_log(tmp_path, log_text or make_log(pages=1))
    gate = QualityGate(extractor=FakeExtractor(pages))
    return gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))


class TestTheMapping:
    def test_every_code_has_a_severity(self):
        for code in QualityIssueCode:
            assert code in SEVERITY_BY_CODE

    def test_orphan_words_are_the_only_warning(self):
        warnings = [
            code
            for code, severity in SEVERITY_BY_CODE.items()
            if severity is QualitySeverity.WARNING
        ]
        assert warnings == [QualityIssueCode.ORPHAN_WORD]

    def test_a_broken_layout_always_blocks(self):
        for code in (
            QualityIssueCode.TEXT_OVERLAP,
            QualityIssueCode.RULE_TEXT_COLLISION,
            QualityIssueCode.INVALID_PAGE_COUNT,
            QualityIssueCode.COMPILATION_FAILED,
            QualityIssueCode.MISSING_GLYPH,
            QualityIssueCode.OVERFULL_HBOX,
        ):
            assert SEVERITY_BY_CODE[code] is QualitySeverity.ERROR


class TestWarningsDoNotBlock:
    def test_an_orphan_alone_still_passes(self, tmp_path):
        # Three of the nine known-good resumes contain orphans while being
        # otherwise clean. A stranded word is cosmetic.
        result = evaluate(tmp_path, [orphan_page()])
        assert result.passed is True

    def test_the_orphan_is_still_reported(self, tmp_path):
        result = evaluate(tmp_path, [orphan_page()])
        assert QualityIssueCode.ORPHAN_WORD in [i.code for i in result.issues]

    def test_it_lands_in_warnings_not_errors(self, tmp_path):
        result = evaluate(tmp_path, [orphan_page()])
        assert len(result.warnings) == 1
        assert result.errors == []


class TestErrorsBlock:
    def test_an_overlap_fails_even_on_one_page(self, tmp_path):
        page = make_page(
            [make_line(baseline=700.0), make_line(baseline=696.0)], rules=[make_rule()]
        )
        result = evaluate(tmp_path, [page])
        assert result.passed is False
        assert result.errors

    def test_passed_is_exactly_no_errors(self, tmp_path):
        result = evaluate(tmp_path, [orphan_page()])
        assert result.passed == (len(result.errors) == 0)

    def test_an_error_beside_a_warning_still_fails(self, tmp_path):
        result = evaluate(
            tmp_path, [orphan_page()], make_log(pages=1, missing_glyphs=["^^c3"])
        )
        assert result.passed is False
        assert result.warnings and result.errors


class TestOrdering:
    def test_errors_sort_before_warnings(self, tmp_path):
        result = evaluate(
            tmp_path, [orphan_page()], make_log(pages=1, missing_glyphs=["^^c3"])
        )
        severities = [i.severity for i in result.issues]
        assert severities == sorted(severities, key=lambda s: s.value)
        assert severities[0] is QualitySeverity.ERROR
