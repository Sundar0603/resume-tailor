"""
Error versus failure.

A *failure* is a result with ``passed=False``: the resume was evaluated and is
not submission-ready. An *error* is a raise: the evaluation could not be
performed. The task doc is explicit that an analyzer failure must never be
reported as a successful quality result — a gate that cannot read the PDF knows
nothing about the PDF, which is not the same as knowing the PDF is fine.
"""

import pytest

from src.quality import QualityGate
from src.quality.exceptions import (
    GeometryUnavailableError,
    PDFUnreadableError,
    QualityAnalysisError,
    QualityGateError,
)
from src.quality.geometry import pdfminer_extractor

from .conftest import (
    FailingExtractor,
    FakeExtractor,
    make_compilation_result,
    make_line,
    make_log,
    make_page,
    make_rule,
    write_log,
)


class TestUnreadablePDFs:
    def test_a_missing_file_raises(self, tmp_path):
        with pytest.raises(PDFUnreadableError):
            pdfminer_extractor(str(tmp_path / "nope.pdf"))

    def test_bytes_that_are_not_a_pdf_raise(self, tmp_path):
        path = tmp_path / "junk.pdf"
        path.write_bytes(b"this is not a PDF at all")
        with pytest.raises(PDFUnreadableError):
            pdfminer_extractor(str(path))

    def test_the_degenerate_pdf_the_compiler_accepts_raises_here(self, tmp_path):
        # The Compiler deliberately passes a file with valid magic bytes and no
        # content: "the compiler is not the Quality Gate and must not care".
        # Judging it is this package's job, and the honest verdict is an error.
        path = tmp_path / "degenerate.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        with pytest.raises(PDFUnreadableError):
            pdfminer_extractor(str(path))


class TestErrorsAreNeverSwallowed:
    def test_an_extractor_failure_propagates(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=1))
        gate = QualityGate(extractor=FailingExtractor(PDFUnreadableError("bad")))
        with pytest.raises(PDFUnreadableError):
            gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))

    def test_a_missing_backend_propagates(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=1))
        gate = QualityGate(extractor=FailingExtractor(GeometryUnavailableError("no")))
        with pytest.raises(GeometryUnavailableError):
            gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))

    def test_an_analyser_failure_never_returns_a_pass(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=1))
        gate = QualityGate(extractor=FailingExtractor(PDFUnreadableError("bad")))
        try:
            result = gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))
        except QualityGateError:
            return
        raise AssertionError(
            "expected a raise, got passed={0}".format(result.passed)
        )


class TestInconsistentArtifacts:
    def test_a_page_count_disagreement_raises(self, tmp_path):
        # The log describes a different compilation than the PDF. Quietly
        # choosing one would make the metric untrustworthy exactly when it
        # matters.
        path = write_log(tmp_path, make_log(pages=5))
        gate = QualityGate(
            extractor=FakeExtractor([make_page([make_line()], rules=[make_rule()])])
        )
        with pytest.raises(QualityAnalysisError):
            gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))

    def test_a_log_without_a_page_count_defers_to_the_pdf(self, tmp_path):
        path = write_log(tmp_path, make_log(pages=None))
        gate = QualityGate(
            extractor=FakeExtractor([make_page([make_line()], rules=[make_rule()])])
        )
        result = gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))
        assert result.metrics.page_count == 1


class TestTheExceptionTree:
    def test_every_error_shares_one_base(self):
        for error in (
            GeometryUnavailableError,
            PDFUnreadableError,
            QualityAnalysisError,
        ):
            assert issubclass(error, QualityGateError)
