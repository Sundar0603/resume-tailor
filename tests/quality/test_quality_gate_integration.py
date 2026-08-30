"""
Integration tests for the Quality Gate.

These render, compile and analyse real PDFs. There are no pytest markers
registered in pyproject.toml, so the project's way of marking an integration
test is a module-level skipif — the same one the compiler and renderer suites
use.
"""

import glob
import os
import shutil

import pytest

from src.compiler import PDFCompiler
from src.parser import ResumeParser
from src.quality import QualityGate, QualityIssueCode
from src.quality.checks import find_overlaps
from src.quality.geometry import pdfminer_extractor
from src.renderer import LatexRenderer

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)

BROKEN_FIXTURE = "tests/fixtures/latex/overlapping_bullets.tex"
CANONICAL = "content/backend_resume.md"


def compile_source(latex, tmp_path, name="resume"):
    return PDFCompiler().compile(latex, output_directory=str(tmp_path), job_name=name)


def evaluate(latex, tmp_path, name="resume"):
    result = compile_source(latex, tmp_path, name)
    return QualityGate().evaluate(result.pdf_path, result.tex_path, result)


class TestTheBrokenOnePageRegression:
    """
    The mandatory regression from §10d.

    Per-bullet negative vspace made consecutive bullets print on top of each
    other. pdflatex exited 0, reported no warnings, and the page count went
    from two to one — the metric *improved* because the text was collapsing
    onto itself. A test asserting ``pages == 1`` passed on that document and
    locked the bug in.

    This is what stops page count becoming the sole success signal again.
    """

    def test_the_fixture_really_is_one_page(self, tmp_path):
        latex = open(BROKEN_FIXTURE).read()
        result = evaluate(latex, tmp_path, "broken")
        assert result.metrics.page_count == 1

    def test_the_fixture_reports_no_overfull_boxes(self, tmp_path):
        # Negative vspace never produces an overfull warning, which is why the
        # log cannot catch this and the geometry must.
        latex = open(BROKEN_FIXTURE).read()
        assert evaluate(latex, tmp_path, "broken").metrics.overfull_hbox_count == 0

    def test_a_one_page_pdf_with_colliding_text_fails(self, tmp_path):
        latex = open(BROKEN_FIXTURE).read()
        assert evaluate(latex, tmp_path, "broken").passed is False

    def test_the_failure_is_a_text_overlap(self, tmp_path):
        latex = open(BROKEN_FIXTURE).read()
        result = evaluate(latex, tmp_path, "broken")
        assert QualityIssueCode.TEXT_OVERLAP in [i.code for i in result.issues]

    def test_the_overlap_is_counted(self, tmp_path):
        latex = open(BROKEN_FIXTURE).read()
        assert evaluate(latex, tmp_path, "broken").metrics.overlap_count > 0


class TestARealResume:
    def test_a_canonical_resume_compiles_and_is_evaluated(self, tmp_path):
        resume = ResumeParser().parse(CANONICAL)
        result = evaluate(LatexRenderer().render(resume), tmp_path)
        assert result.metrics.total_text_lines > 0

    def test_it_runs_to_two_pages_today(self, tmp_path):
        # The honest number: the masters reach one page only through hand-tuned
        # spacing the renderer does not invent. Fitting is the trimmer's job.
        resume = ResumeParser().parse(CANONICAL)
        result = evaluate(LatexRenderer().render(resume), tmp_path)
        assert result.metrics.page_count == 2

    def test_a_two_page_resume_fails_on_page_count(self, tmp_path):
        resume = ResumeParser().parse(CANONICAL)
        result = evaluate(LatexRenderer().render(resume), tmp_path)
        assert QualityIssueCode.INVALID_PAGE_COUNT in [i.code for i in result.issues]

    def test_a_clean_resume_reports_no_overlap(self, tmp_path):
        resume = ResumeParser().parse(CANONICAL)
        result = evaluate(LatexRenderer().render(resume), tmp_path)
        assert result.metrics.overlap_count == 0

    def test_the_overflowing_sections_are_named(self, tmp_path):
        resume = ResumeParser().parse(CANONICAL)
        result = evaluate(LatexRenderer().render(resume), tmp_path)
        assert result.metrics.overflowing_sections

    def test_evaluation_is_deterministic_over_real_artifacts(self, tmp_path):
        resume = ResumeParser().parse(CANONICAL)
        latex = LatexRenderer().render(resume)
        compiled = compile_source(latex, tmp_path)
        gate = QualityGate()
        first = gate.evaluate(compiled.pdf_path, compiled.tex_path, compiled)
        second = gate.evaluate(compiled.pdf_path, compiled.tex_path, compiled)
        assert first == second


class TestTheKnownGoodCorpus:
    """
    The calibration corpus as a standing regression.

    All nine previously-compiled resumes are known good: zero overfull boxes,
    zero missing glyphs. The overlap threshold was chosen so that every one of
    them reports zero collisions while the broken fixture reports several. If
    a change to the rule starts flagging these, it has become a false-positive
    generator.
    """

    def test_no_known_good_pdf_reports_an_overlap(self):
        found = sorted(glob.glob("output/compile/*/*.pdf"))
        if not found:
            pytest.skip("the compiled corpus under output/ is not present")
        for pdf in found:
            overlaps = find_overlaps(pdfminer_extractor(pdf))
            assert overlaps == [], "{0} reported {1} overlap(s)".format(
                os.path.basename(pdf), len(overlaps)
            )
