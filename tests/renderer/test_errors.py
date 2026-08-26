"""
SerializationError covers values canonical Markdown cannot carry.

Each case here was verified against the parser: writing the value out and
reading it back loses content silently. Raising makes the loss loud. Resume
*validity* remains the Validator's job — these are round-trip failures, not
schema violations.
"""

import pytest

from src.renderer import MarkdownSerializer, SerializationError
from src.renderer.exceptions import RendererError

from .conftest import make_resume


class TestEmptyBullets:
    def test_an_empty_highlight_raises(self):
        # '- ' strips to '-', which fails the parser's bullet test and breaks
        # the loop, silently dropping every later bullet in the list.
        resume = make_resume()
        resume.experiences[0].highlights = ["Real bullet.", "", "Also real."]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_whitespace_only_highlight_raises(self):
        resume = make_resume()
        resume.projects[0].highlights = ["   "]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_an_empty_technology_raises(self):
        resume = make_resume()
        resume.experiences[0].technologies = ["Java", ""]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_an_empty_skill_raises(self):
        resume = make_resume()
        resume.skills[0].skills = ["Redis", ""]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)


class TestSeparatorCollision:
    def test_a_highlight_that_is_only_a_rule_raises(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["First.", "---", "Third."]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_summary_line_that_is_only_a_rule_raises(self):
        resume = make_resume()
        resume.summary = "First part.\n---\nSecond part."
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_scalar_that_is_only_a_rule_raises(self):
        resume = make_resume()
        resume.experiences[0].location = "---"
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)


class TestLineBreaks:
    def test_a_newline_in_a_scalar_raises(self):
        resume = make_resume()
        resume.experiences[0].company = "Zoho\nCorporation"
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_newline_in_a_highlight_raises(self):
        resume = make_resume()
        resume.projects[0].highlights = ["Line one\nLine two"]
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_newline_in_a_skill_category_name_raises(self):
        resume = make_resume()
        resume.skills[0].category = "Sec\nurity"
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_a_carriage_return_raises(self):
        resume = make_resume()
        resume.contact.name = "Sundar\rS"
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)


class TestEmptyRequiredFields:
    def test_an_empty_required_scalar_raises_rather_than_being_dropped(self):
        resume = make_resume()
        resume.experiences[0].company = ""
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_an_empty_contact_field_raises(self):
        resume = make_resume()
        resume.contact.email = ""
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_an_empty_summary_raises(self):
        resume = make_resume()
        resume.summary = "   "
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)

    def test_an_empty_skill_category_name_raises(self):
        resume = make_resume()
        resume.skills[0].category = ""
        with pytest.raises(SerializationError):
            MarkdownSerializer().serialize(resume)


class TestErrorShape:
    def test_it_subclasses_the_package_base(self):
        assert issubclass(SerializationError, RendererError)

    def test_the_message_names_the_entity_and_field(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["ok", ""]
        try:
            MarkdownSerializer().serialize(resume)
        except SerializationError as exc:
            message = str(exc)
        assert "exp_001" in message
        assert "highlights" in message

    def test_the_message_falls_back_when_no_id_is_set(self):
        resume = make_resume()
        resume.experiences[0].id = ""
        resume.experiences[0].company = ""
        try:
            MarkdownSerializer().serialize(resume)
        except SerializationError as exc:
            message = str(exc)
        assert "experience" in message
