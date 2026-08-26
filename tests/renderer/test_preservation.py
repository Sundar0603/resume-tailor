"""
Content preservation: the serializer is not an editor.

Nothing is shortened, re-cased, re-punctuated, wrapped or normalised.
"""

from src.parser import ResumeParser
from src.renderer import MarkdownSerializer

from .conftest import make_resume


class TestTextPreservation:
    def test_bullet_text_is_exact(self):
        resume = make_resume()
        bullet = "Cut p99 latency by 40% across 12 services, end-to-end."
        resume.experiences[0].highlights = [bullet]
        markdown = MarkdownSerializer().serialize(resume)
        assert "- " + bullet in markdown

    def test_punctuation_survives(self):
        resume = make_resume()
        bullet = "Built X (Y), Z — and Q; then \"R\" & 'S'!"
        resume.projects[0].highlights = [bullet]
        markdown = MarkdownSerializer().serialize(resume)
        assert "- " + bullet in markdown

    def test_capitalisation_is_untouched(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["BUILT an API using gRPC and OAuth2."]
        markdown = MarkdownSerializer().serialize(resume)
        assert "- BUILT an API using gRPC and OAuth2." in markdown

    def test_urls_survive_intact(self):
        resume = make_resume()
        url = "https://github.com/a/b?x=1&y=2#frag"
        resume.projects[0].repository = url
        markdown = MarkdownSerializer().serialize(resume)
        assert "Repository: " + url in markdown

    def test_a_value_containing_a_colon_survives(self):
        resume = make_resume()
        resume.experiences[0].role = "Engineer: Level 3"
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(resume)
        )
        assert reparsed.experiences[0].role == "Engineer: Level 3"

    def test_technology_and_domain_names_are_exact(self):
        resume = make_resume()
        resume.experiences[0].technologies = ["Node.js", "C++", "ASP.NET Core"]
        resume.experiences[0].domains = ["CI/CD", "A/B Testing"]
        markdown = MarkdownSerializer().serialize(resume)
        for term in ("Node.js", "C++", "ASP.NET Core", "CI/CD", "A/B Testing"):
            assert "- " + term in markdown

    def test_a_long_summary_is_not_wrapped(self):
        resume = make_resume()
        resume.summary = "word " * 200
        resume.summary = resume.summary.strip()
        markdown = MarkdownSerializer().serialize(resume)
        assert resume.summary in markdown
        body = markdown.split("# Summary\n\n")[1].split("\n\n---")[0]
        assert "\n" not in body

    def test_summary_is_never_turned_into_bullets(self):
        resume = make_resume()
        resume.summary = "First point. Second point. Third point."
        markdown = MarkdownSerializer().serialize(resume)
        body = markdown.split("# Summary\n\n")[1].split("\n\n---")[0]
        assert body == resume.summary


class TestNoNormalisation:
    def test_a_trailing_period_is_neither_added_nor_removed(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["No trailing period", "Has one."]
        markdown = MarkdownSerializer().serialize(resume)
        assert "- No trailing period\n" in markdown
        assert "- Has one.\n" in markdown

    def test_internal_double_spaces_survive(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["Built  the  thing."]
        markdown = MarkdownSerializer().serialize(resume)
        assert "- Built  the  thing." in markdown

    def test_non_ascii_characters_survive(self):
        resume = make_resume()
        resume.contact.name = "Sundar Ş — 中文"
        markdown = MarkdownSerializer().serialize(resume)
        assert "Name: Sundar Ş — 中文" in markdown


class TestRuntimeMetadataIsNotLeaked:
    def test_entity_ids_never_appear(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        for entity_id in ("skill_001", "exp_001", "proj_001", "edu_001"):
            assert entity_id not in markdown

    def test_entity_source_never_appears(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert "CANONICAL" not in markdown
        assert "GENERATED" not in markdown
        assert "source" not in markdown
