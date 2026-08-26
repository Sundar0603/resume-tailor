"""
The renderer never emits per-bullet negative vertical space.

This guards a bug that every other check missed. Emitting the masters'
hand-placed ``\\vspace{-12px}`` after *every* project bullet made consecutive
multi-line bullets print on top of each other. pdflatex reported nothing —
negative vspace produces no overfull warning — brace balance was fine, and the
page count *improved*, because the text was collapsing onto itself rather than
fitting. Only looking at the rendered PDF caught it.

So the invariant is structural, and checkable without a TeX distribution: a
bullet's content line must not carry trailing negative spacing. Spacing after a
project *title* is fine and is what the masters actually do.
"""

import re

from src.parser import ResumeParser
from src.renderer import LatexRenderer

from .conftest import CANONICAL_RESUMES, make_resume, make_sparse_resume

BULLET_WITH_TRAILING_VSPACE = re.compile(r"\\resumeItem\{\\normalsize\{.*\}\}\s*\\vspace\{-")


def bullet_lines(latex):
    """Content bullets only — a project title is a resumeItem too, but not a bullet."""
    return [
        line
        for line in latex.splitlines()
        if "\\resumeItem{\\normalsize{" in line and "\\textbf{" not in line
    ]


class TestNoPerBulletCompression:
    def test_no_content_bullet_carries_negative_vspace(self):
        for resume in [make_resume(), make_sparse_resume()]:
            latex = LatexRenderer().render(resume)
            for line in bullet_lines(latex):
                assert not BULLET_WITH_TRAILING_VSPACE.search(line), line

    def test_canonical_resumes_have_no_bullet_compression(self):
        for path in CANONICAL_RESUMES:
            latex = LatexRenderer().render(ResumeParser().parse(path))
            for line in bullet_lines(latex):
                assert "\\vspace{-" not in line, "{}: {}".format(path, line)

    def test_bullets_are_emitted_one_per_line(self):
        # Two bullets sharing a line would defeat the check above.
        latex = LatexRenderer().render(make_resume())
        for line in latex.splitlines():
            assert line.count("\\resumeItem{") <= 1, line


class TestStructuralSpacingIsKept:
    def test_project_titles_keep_their_spacing(self):
        latex = LatexRenderer().render(make_resume())
        assert "\\vspace{-4px}" in latex

    def test_the_experience_list_keeps_its_lead(self):
        latex = LatexRenderer().render(make_resume())
        assert "\\vspace{-1pt}" in latex
