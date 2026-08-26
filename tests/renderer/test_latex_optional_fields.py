"""
Optional fields and empty collections produce valid LaTeX, never 'None'.

The template's macros take a fixed argument count, so an absent optional value
becomes an empty argument rather than a missing one. Empty *collections* are
the sharper edge: ``\\begin{itemize}`` with no ``\\item`` is a LaTeX error, not
an empty list, so a list environment is omitted rather than emitted empty.
"""

import pytest

from src.renderer import LatexRenderer, RenderingError

from .conftest import make_resume, make_sparse_resume


class TestNoneIsNeverWritten:
    def test_the_word_none_never_appears(self):
        latex = LatexRenderer().render(make_sparse_resume())
        assert "None" not in latex
        assert "null" not in latex

    def test_a_sparse_resume_renders_completely(self):
        latex = LatexRenderer().render(make_sparse_resume())
        assert latex.strip().endswith("\\end{document}")


class TestOptionalScalars:
    def test_an_absent_location_becomes_an_empty_argument(self):
        resume = make_resume()
        resume.experiences[0].location = None
        latex = LatexRenderer().render(resume)
        assert "{" + resume.experiences[0].company + "}{}" in latex

    def test_an_empty_location_is_treated_as_absent(self):
        resume = make_resume()
        resume.experiences[0].location = ""
        latex = LatexRenderer().render(resume)
        assert "{" + resume.experiences[0].company + "}{}" in latex

    def test_an_absent_cgpa_removes_the_whole_fragment(self):
        resume = make_resume()
        resume.education[0].cgpa = None
        latex = LatexRenderer().render(resume)
        assert "CGPA" not in latex
        assert "\\textnormal" not in latex

    def test_an_absent_repository_emits_no_link(self):
        resume = make_resume()
        for project in resume.projects:
            project.repository = None
        latex = LatexRenderer().render(resume)
        assert "\\underline{Link}" not in latex


class TestEmptyCollections:
    def test_a_project_with_no_technologies_omits_the_parenthetical(self):
        resume = make_resume()
        resume.projects[0].technologies = []
        latex = LatexRenderer().render(resume)
        assert "\\textit{()}" not in latex
        assert "\\textbf{" + resume.projects[0].name + "}}" in latex

    def test_a_category_with_no_skills_still_renders_a_valid_row(self):
        resume = make_resume()
        resume.skills[0].skills = []
        latex = LatexRenderer().render(resume)
        assert "\\textbf{\\normalsize{" + resume.skills[0].category + ":}}{ \\normalsize{}}" in latex

    def test_an_entry_with_no_highlights_emits_no_empty_itemize(self):
        full = LatexRenderer().render(make_resume())
        resume = make_resume()
        resume.experiences[0].highlights = []
        emptied = LatexRenderer().render(resume)
        assert emptied.count("\\resumeItemListStart") == (
            full.count("\\resumeItemListStart") - 1
        )

    def test_list_environments_always_balance(self):
        resume = make_resume()
        resume.experiences[0].highlights = []
        resume.projects[0].highlights = []
        latex = LatexRenderer().render(resume)
        assert latex.count("\\resumeItemListStart") == latex.count(
            "\\resumeItemListEnd"
        )
        assert latex.count("\\resumeSubHeadingListStart") == latex.count(
            "\\resumeSubHeadingListEnd"
        )


class TestSectionsTheTemplateCannotLeaveEmpty:
    """The template opens the list environment, so an empty section cannot compile."""

    def test_no_experiences_raises(self):
        resume = make_resume()
        resume.experiences = []
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_no_projects_raises(self):
        resume = make_resume()
        resume.projects = []
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_no_education_raises(self):
        resume = make_resume()
        resume.education = []
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_an_empty_summary_raises(self):
        resume = make_resume()
        resume.summary = "   "
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_an_empty_highlight_raises(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["Real one", "   "]
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_an_empty_category_name_raises(self):
        resume = make_resume()
        resume.skills[0].category = "  "
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)


class TestBraceBalance:
    """A proxy for compilability, since pdflatex is not available in CI."""

    def test_braces_balance_across_the_document(self):
        for resume in [make_resume(), make_sparse_resume()]:
            latex = LatexRenderer().render(resume)
            depth = 0
            index = 0
            while index < len(latex):
                character = latex[index]
                if character == "\\" and index + 1 < len(latex):
                    index += 2  # skip an escaped or command character
                    continue
                if character == "%":
                    index = latex.find("\n", index)
                    if index == -1:
                        break
                    continue
                if character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    assert depth >= 0
                index += 1
            assert depth == 0
