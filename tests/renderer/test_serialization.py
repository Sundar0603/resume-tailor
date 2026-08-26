"""
Basic serialization: every section renders, and the front matter is correct.
"""

from src.renderer import MarkdownSerializer

from .conftest import make_resume


class TestFrontMatter:
    def test_emits_a_delimited_yaml_block_first(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        lines = markdown.splitlines()
        assert lines[0] == "---"
        assert lines[1] == "resume: backend"
        assert lines[2] == "template: backend"
        assert lines[3] == "version: 1.0"
        assert lines[4] == "---"

    def test_uses_the_values_from_the_resume(self):
        resume = make_resume()
        resume.metadata.resume = "cybersecurity"
        resume.metadata.template = "cybersecurity"
        markdown = MarkdownSerializer().serialize(resume)
        assert "resume: cybersecurity" in markdown
        assert "template: cybersecurity" in markdown

    def test_leaves_ordinary_values_unquoted(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert 'resume: "backend"' not in markdown

    def test_quotes_a_version_yaml_would_retype(self):
        # Bare 1.10 loads as the float 1.1, so the string would not survive.
        resume = make_resume()
        resume.metadata.version = "1.10"
        markdown = MarkdownSerializer().serialize(resume)
        assert 'version: "1.10"' in markdown

    def test_quotes_a_value_yaml_would_read_as_a_boolean(self):
        resume = make_resume()
        resume.metadata.template = "no"
        markdown = MarkdownSerializer().serialize(resume)
        assert 'template: "no"' in markdown


class TestSections:
    def test_every_section_heading_is_present(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        for heading in (
            "# Contact",
            "# Summary",
            "# Skills",
            "# Work Experience",
            "# Projects",
            "# Education",
        ):
            assert heading in markdown

    def test_contact_fields_use_the_schema_labels(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert "Name: Sundar S" in markdown
        assert "Phone: +91 7397398343" in markdown
        assert "Email: sundars0603@gmail.com" in markdown
        assert "LinkedIn: https://www.linkedin.com/in/sundar-s-870042235/" in markdown
        assert "GitHub: https://github.com/Sundar0603" in markdown

    def test_summary_is_a_paragraph_not_bullets(self):
        resume = make_resume()
        markdown = MarkdownSerializer().serialize(resume)
        body = markdown.split("# Summary\n\n")[1].split("\n\n---")[0]
        assert body == resume.summary
        assert not body.startswith("- ")

    def test_skill_categories_are_h2_headings(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert "## Security" in markdown
        assert "## Backend" in markdown
        assert "- SOC Tooling" in markdown

    def test_experience_blocks_use_the_literal_heading(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.count("## Experience") == 2
        assert "Company: Zoho Corporation" in markdown
        assert "Employment Type: Full Time" in markdown

    def test_project_blocks_use_the_literal_heading(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.count("## Project\n") == 2
        assert "Name: Triage Studio" in markdown
        assert "Type: Personal" in markdown

    def test_education_blocks_use_the_literal_heading(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert "## Degree" in markdown
        assert "Institution: Anna University" in markdown
        assert "CGPA: 9.18" in markdown


class TestDocumentShape:
    def test_ends_with_exactly_one_newline(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.endswith("\n")
        assert not markdown.endswith("\n\n")

    def test_no_line_carries_trailing_whitespace(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        for line in markdown.splitlines():
            assert line == line.rstrip()

    def test_returns_a_string(self):
        assert isinstance(MarkdownSerializer().serialize(make_resume()), str)
