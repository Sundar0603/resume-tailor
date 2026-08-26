"""
LaTeX-sensitive content is escaped; URLs are not corrupted by that escaping.

The two rules pull in opposite directions. ``_`` and ``&`` must be escaped in
body text and must survive untouched inside ``\\href``'s first argument, so the
renderer keeps two escapers and this file pins both.
"""

import pytest

from src.renderer import LatexRenderer, RenderingError

from .conftest import make_resume

SPECIALS = ["&", "%", "$", "#", "_", "{", "}", "~", "^", "\\"]


def render_summary(text):
    resume = make_resume()
    resume.summary = text
    return LatexRenderer().render(resume)


class TestBodyTextEscaping:
    def test_each_special_character_is_escaped(self):
        expected = {
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
            "~": "\\textasciitilde{}",
            "^": "\\textasciicircum{}",
            "\\": "\\textbackslash{}",
        }
        for character, escape in expected.items():
            latex = render_summary("before " + character + " after")
            assert "before " + escape + " after" in latex

    def test_a_backslash_is_not_double_escaped(self):
        latex = render_summary("100\\% done")
        assert "100\\textbackslash{}\\% done" in latex

    def test_all_specials_together_survive(self):
        latex = render_summary("".join(SPECIALS))
        assert "\\&\\%\\$\\#\\_\\{\\}" in latex

    def test_specials_in_a_highlight_are_escaped(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["Cut cost by 50% & raised R&D_spend"]
        latex = LatexRenderer().render(resume)
        assert "Cut cost by 50\\% \\& raised R\\&D\\_spend" in latex

    def test_specials_in_a_skill_are_escaped(self):
        resume = make_resume()
        resume.skills[0].skills = ["C#", "AT&T Unix"]
        latex = LatexRenderer().render(resume)
        assert "C\\#, AT\\&T Unix" in latex

    def test_specials_in_a_category_name_are_escaped(self):
        resume = make_resume()
        resume.skills[0].category = "R&D"
        latex = LatexRenderer().render(resume)
        assert "\\textbf{\\normalsize{R\\&D:}}" in latex

    def test_template_markup_is_not_escaped(self):
        # Only resume content is escaped. The template's own macros must survive.
        latex = LatexRenderer().render(make_resume())
        assert "\\resumeSubHeadingListStart" in latex
        assert "\\textbackslash{}resumeSubHeadingListStart" not in latex


class TestUrlEscaping:
    def test_url_characters_survive_intact(self):
        resume = make_resume()
        url = "https://example.com/a_b?x=1&y=2#frag"
        resume.projects[0].repository = url
        latex = LatexRenderer().render(resume)
        # '#' is the one character hyperref cannot take raw.
        assert "\\href{https://example.com/a_b?x=1&y=2\\#frag}" in latex

    def test_underscores_in_a_url_are_not_escaped(self):
        resume = make_resume()
        resume.projects[0].repository = "https://github.com/me/my_repo_name"
        latex = LatexRenderer().render(resume)
        assert "my_repo_name" in latex
        assert "my\\_repo\\_name" not in latex

    def test_a_percent_in_a_url_is_escaped(self):
        resume = make_resume()
        resume.projects[0].repository = "https://example.com/a%20b"
        latex = LatexRenderer().render(resume)
        assert "\\href{https://example.com/a\\%20b}" in latex

    def test_contact_links_keep_their_query_characters(self):
        resume = make_resume()
        resume.contact.linkedin = "https://linkedin.com/in/me?trk=nav&x=1"
        latex = LatexRenderer().render(resume)
        assert "\\href{https://linkedin.com/in/me?trk=nav&x=1}" in latex


class TestUnicode:
    def test_known_punctuation_is_transliterated(self):
        expected = {
            "\u2013": "--",
            "\u2014": "---",
            "\u2019": "'",
            "\u201c": "``",
            "\u201d": "''",
            "\u2026": "\\ldots{}",
        }
        for character, replacement in expected.items():
            latex = render_summary("a " + character + " b")
            assert "a " + replacement + " b" in latex

    def test_an_unsupported_character_raises(self):
        with pytest.raises(RenderingError):
            render_summary("Delivered 日本語 support")

    def test_an_unsupported_character_in_a_highlight_raises(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["Improved throughput by ≥40%"]
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_the_error_names_the_field(self):
        resume = make_resume()
        resume.contact.name = "Renée ☃"
        try:
            LatexRenderer().render(resume)
        except RenderingError as error:
            assert "contact.name" in str(error)
        else:
            raise AssertionError("expected RenderingError")

    def test_output_is_pure_ascii(self):
        latex = LatexRenderer().render(make_resume())
        latex.encode("ascii")
