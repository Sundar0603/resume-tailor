"""
Optional fields are omitted when absent, and 'None' is never written.

Omission is not cosmetic. The parser's scalar pattern is ``^Key:\\s*(.+)$``
with ``\\s`` spanning newlines, so a bare ``Repository:`` line swallows the
whole of the next field's line.
"""

from src.parser import ResumeParser
from src.renderer import MarkdownSerializer

from .conftest import make_resume, make_sparse_resume


class TestOmission:
    def test_absent_location_produces_no_line(self):
        resume = make_resume()
        resume.experiences[0].location = None
        markdown = MarkdownSerializer().serialize(resume)
        block = markdown.split("## Experience\n\n")[1].split("## Experience")[0]
        assert "Location:" not in block

    def test_absent_repository_produces_no_line(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        socrates = markdown.split("Name: SOCrates")[1]
        assert "Repository:" not in socrates.split("# Education")[0]

    def test_absent_cgpa_produces_no_line(self):
        resume = make_resume()
        resume.education[0].cgpa = None
        markdown = MarkdownSerializer().serialize(resume)
        assert "CGPA:" not in markdown

    def test_empty_string_is_treated_as_absent(self):
        # 'Location: ' with a trailing space parses back as '', not None, and
        # would also carry trailing whitespace. Omitting is the only clean move.
        resume = make_resume()
        resume.experiences[0].location = ""
        markdown = MarkdownSerializer().serialize(resume)
        block = markdown.split("## Experience\n\n")[1].split("## Experience")[0]
        assert "Location:" not in block

    def test_empty_list_fields_produce_no_block(self):
        resume = make_resume()
        resume.experiences[0].technologies = []
        resume.experiences[0].domains = []
        markdown = MarkdownSerializer().serialize(resume)
        block = markdown.split("## Experience\n\n")[1].split("## Experience")[0]
        assert "Technologies:" not in block
        assert "Domains:" not in block

    def test_empty_skill_category_produces_only_a_heading(self):
        resume = make_resume()
        resume.skills[0].skills = []
        markdown = MarkdownSerializer().serialize(resume)
        assert "## Security\n\n## Backend" in markdown

    def test_empty_projects_section_still_renders_its_heading(self):
        resume = make_resume()
        resume.projects = []
        markdown = MarkdownSerializer().serialize(resume)
        assert "# Projects" in markdown
        assert "## Project" not in markdown


class TestNoneIsNeverWritten:
    def test_the_word_none_never_appears(self):
        markdown = MarkdownSerializer().serialize(make_sparse_resume())
        assert "None" not in markdown
        assert "null" not in markdown

    def test_no_label_is_left_dangling(self):
        markdown = MarkdownSerializer().serialize(make_sparse_resume())
        for line in markdown.splitlines():
            if line.endswith(":") and line.startswith(("Repository", "Location", "CGPA")):
                raise AssertionError("dangling label: " + line)


class TestSparseRoundTrip:
    def test_absent_fields_stay_absent_after_reparsing(self):
        original = make_sparse_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert reparsed.experiences[0].location is None
        assert reparsed.projects[0].repository is None
        assert reparsed.education[0].cgpa is None
        assert reparsed.education[0].location is None

    def test_a_following_field_is_not_swallowed(self):
        resume = make_resume()
        resume.projects[0].repository = None
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(resume)
        )
        assert reparsed.projects[0].type == "Personal"
        assert reparsed.projects[0].repository is None
