"""
Integration tests for the PDF Compiler.

These invoke a real TeX engine. There are no pytest markers registered in
pyproject.toml, so the project's way of marking an integration test is a
module-level skipif — the same one the renderer's compilation tests use.
"""

import shutil

import pytest

from src.compiler import (
    CompilationFailedError,
    PDFCompiler,
    PDFNotGeneratedError,
)

from .conftest import BROKEN_DOCUMENT, MINIMAL_DOCUMENT

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)


class TestRealCompilation:
    def test_a_minimal_document_compiles(self, tmp_path):
        result = PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert result.exit_code == 0

    def test_the_pdf_exists_and_is_readable(self, tmp_path):
        result = PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        pdf = tmp_path / "resume.pdf"
        assert pdf.is_file()
        assert pdf.stat().st_size > 0
        assert pdf.read_bytes()[:5] == b"%PDF-"
        assert result.pdf_path == str(pdf)

    def test_the_source_and_log_are_preserved(self, tmp_path):
        PDFCompiler().compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert (tmp_path / "resume.tex").read_text(encoding="utf-8") == MINIMAL_DOCUMENT
        assert "This is pdfTeX" in (tmp_path / "resume.log").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_no_auxiliary_files_leak_into_the_output_directory(self, tmp_path):
        PDFCompiler().compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "resume.log",
            "resume.pdf",
            "resume.tex",
        ]

    def test_the_job_name_is_honoured(self, tmp_path):
        PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path), job_name="attempt_3"
        )
        assert (tmp_path / "attempt_3.pdf").is_file()


class TestRealFailure:
    def test_a_broken_document_raises(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            PDFCompiler().compile(BROKEN_DOCUMENT, output_directory=str(tmp_path))

    def test_it_is_not_reported_as_a_missing_pdf(self, tmp_path):
        # The distinction matters: LaTeX rejected the document, which is a
        # different diagnosis from LaTeX succeeding and producing nothing.
        with pytest.raises(CompilationFailedError) as caught:
            PDFCompiler().compile(BROKEN_DOCUMENT, output_directory=str(tmp_path))
        assert not isinstance(caught.value, PDFNotGeneratedError)

    def test_the_log_survives_and_names_the_error(self, tmp_path):
        try:
            PDFCompiler().compile(BROKEN_DOCUMENT, output_directory=str(tmp_path))
        except CompilationFailedError as exc:
            log = open(exc.log_path, encoding="utf-8", errors="replace").read()
            assert "Undefined control sequence" in log
            assert exc.exit_code != 0
        else:
            raise AssertionError("expected CompilationFailedError")

    def test_the_source_survives_for_debugging(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            PDFCompiler().compile(BROKEN_DOCUMENT, output_directory=str(tmp_path))
        assert (tmp_path / "resume.tex").read_text(encoding="utf-8") == BROKEN_DOCUMENT


class TestRealDeterminism:
    def test_the_same_source_compiles_to_identical_bytes(self, tmp_path):
        # Without SOURCE_DATE_EPOCH and FORCE_SOURCE_DATE this fails: pdflatex
        # stamps the wall clock into /CreationDate and derives /ID from it.
        first = PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path / "one")
        )
        second = PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path / "two")
        )
        assert open(first.pdf_path, "rb").read() == open(second.pdf_path, "rb").read()

    def test_a_second_compilation_does_not_reuse_the_first_workspace(self, tmp_path):
        first = PDFCompiler().compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path / "one")
        )
        second = PDFCompiler().compile(
            BROKEN_DOCUMENT.replace("\\undefinedcommand", "Different text"),
            output_directory=str(tmp_path / "two"),
        )
        assert first.pdf_path != second.pdf_path
        assert open(first.pdf_path, "rb").read() != open(second.pdf_path, "rb").read()
