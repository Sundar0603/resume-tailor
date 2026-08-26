"""
Template loading, placeholder contracts, and the promise that the template file
on disk is never touched.

The template is the sole authority on visual design, so the renderer must fail
loudly rather than emit a document that is quietly missing a section.
"""

import pytest

from src.renderer import REQUIRED_PLACEHOLDERS, LatexRenderer, RenderingError
from src.renderer.exceptions import RendererError

from .conftest import make_resume

TEMPLATE_NAMES = ["backend", "fullstack", "cybersecurity"]


class TestLoading:
    def test_every_shipped_template_renders(self):
        for name in TEMPLATE_NAMES:
            resume = make_resume()
            resume.metadata.template = name
            latex = LatexRenderer().render(resume)
            assert latex.strip().endswith("\\end{document}")

    def test_a_missing_template_raises(self):
        resume = make_resume()
        resume.metadata.template = "nonexistent"
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_an_empty_template_name_raises(self):
        resume = make_resume()
        resume.metadata.template = "   "
        with pytest.raises(RenderingError):
            LatexRenderer().render(resume)

    def test_a_missing_template_directory_raises(self):
        with pytest.raises(RenderingError):
            LatexRenderer(template_directory="no/such/place").render(make_resume())

    def test_rendering_error_is_a_renderer_error(self):
        resume = make_resume()
        resume.metadata.template = "nonexistent"
        with pytest.raises(RendererError):
            LatexRenderer().render(resume)


class TestPlaceholders:
    def test_a_template_missing_a_placeholder_raises(self, tmp_path):
        # Drop one required placeholder from an otherwise complete template.
        source = (tmp_path / "partial.tex")
        body = "\n".join("{{" + key + "}}" for key in REQUIRED_PLACEHOLDERS[1:])
        source.write_text(body, encoding="utf-8")
        resume = make_resume()
        resume.metadata.template = "partial"
        with pytest.raises(RenderingError):
            LatexRenderer(template_directory=str(tmp_path)).render(resume)

    def test_an_unknown_placeholder_raises(self, tmp_path):
        source = tmp_path / "extra.tex"
        body = "\n".join("{{" + key + "}}" for key in REQUIRED_PLACEHOLDERS)
        source.write_text(body + "\n{{MYSTERY}}\n", encoding="utf-8")
        resume = make_resume()
        resume.metadata.template = "extra"
        with pytest.raises(RenderingError):
            LatexRenderer(template_directory=str(tmp_path)).render(resume)

    def test_no_placeholder_survives_into_the_output(self):
        for name in TEMPLATE_NAMES:
            resume = make_resume()
            resume.metadata.template = name
            assert "{{" not in LatexRenderer().render(resume)


class TestTemplatePreservation:
    def test_the_template_file_is_not_modified(self, tmp_path):
        import shutil

        shutil.copy("templates/backend.tex", tmp_path / "backend.tex")
        before = (tmp_path / "backend.tex").read_bytes()
        LatexRenderer(template_directory=str(tmp_path)).render(make_resume())
        assert (tmp_path / "backend.tex").read_bytes() == before

    def test_the_preamble_survives_verbatim(self):
        template = open("templates/backend.tex", encoding="utf-8").read()
        preamble = template.split("\\begin{document}")[0]
        latex = LatexRenderer().render(make_resume())
        assert latex.startswith(preamble)

    def test_design_declarations_are_untouched(self):
        latex = LatexRenderer().render(make_resume())
        for declaration in [
            "\\documentclass[letterpaper,11pt]{article}",
            "\\usepackage{CormorantGaramond}",
            "\\definecolor{airforceblue}{rgb}{0.36, 0.54, 0.66}",
            "\\addtolength{\\textwidth}{1.19in}",
            "\\newcommand{\\resumeSubheading}[4]{",
            "\\pdfgentounicode=1",
        ]:
            assert declaration in latex


class TestOutputFile:
    def test_render_to_file_writes_the_document(self, tmp_path):
        resume = make_resume()
        path = LatexRenderer().render_to_file(resume, str(tmp_path / "latex"))
        assert path.name == resume.metadata.resume + ".tex"
        assert path.read_text(encoding="utf-8") == LatexRenderer().render(resume)

    def test_render_to_file_creates_missing_directories(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "latex"
        path = LatexRenderer().render_to_file(make_resume(), str(target))
        assert path.is_file()
