"""
Knowledge Base parsing.

Covers the contract task 020 §28 asks for: experiences, projects, skills,
education, ids and source lineage are read correctly, and the failures that
matter are failures rather than silent repairs.
"""

import pytest

from src.knowledge import (
    CanonicalSummary,
    DuplicateEntityId,
    KnowledgeBase,
    KnowledgeBaseNotFoundError,
    KnowledgeBaseParser,
    MalformedEntityId,
    MissingEntityId,
    MissingKnowledgeSection,
    WrappedBullet,
)
from src.parser.models import EntitySource

from .conftest import knowledge_base_text, without_line


def parse(text):
    return KnowledgeBaseParser().parse_string(text)


class TestMetadata:
    def test_front_matter_is_read(self, kb_text):
        kb = parse(kb_text)
        assert kb.metadata.knowledge_base == "test"
        assert kb.metadata.template == "default"
        assert kb.metadata.version == "1.0"

    def test_a_missing_front_matter_field_raises(self, kb_text):
        with pytest.raises(MissingKnowledgeSection):
            parse(without_line(kb_text, "template:"))

    def test_a_document_without_front_matter_raises(self):
        with pytest.raises(MissingKnowledgeSection):
            parse("# Contact\n\nName: Sundar S\n")


class TestContact:
    def test_all_five_fields_are_read(self, kb_text):
        contact = parse(kb_text).contact
        assert contact.name == "Sundar S"
        assert contact.email == "sundarselvam3@gmail.com"
        assert contact.phone == "+91 7397398343"
        assert contact.linkedin.startswith("https://www.linkedin.com/")
        assert contact.github == "https://github.com/Sundar0603"

    def test_a_missing_contact_field_raises(self, kb_text):
        with pytest.raises(MissingKnowledgeSection):
            parse(without_line(kb_text, "GitHub:"))


class TestSummaries:
    def test_every_variant_is_kept(self, kb_text):
        summaries = parse(kb_text).summaries
        assert [s.id for s in summaries] == ["sum_001", "sum_002"]

    def test_a_label_is_optional(self, kb_text):
        summaries = parse(kb_text).summaries
        assert summaries[0].label == "backend emphasis"
        assert summaries[1].label is None

    def test_prose_survives_an_internal_colon(self, kb_text):
        text = parse(kb_text).summaries[0].text
        assert "Comfortable on both sides: building" in text

    def test_separator_rules_are_not_content(self, kb_text):
        for summary in parse(kb_text).summaries:
            assert "---" not in summary.text

    def test_prose_is_joined_into_one_paragraph(self, kb_text):
        assert "\n" not in parse(kb_text).summaries[0].text


class TestSkills:
    def test_categories_and_skills_are_read(self, kb_text):
        skills = parse(kb_text).skills
        assert [c.category for c in skills] == ["Security", "Backend"]
        assert skills[0].skills == ["SOC Tooling", "Threat Intelligence"]

    def test_the_declared_id_is_used(self, kb_text):
        assert [c.id for c in parse(kb_text).skills] == ["skill_001", "skill_002"]


class TestExperiences:
    def test_every_field_is_read(self, kb_text):
        experience = parse(kb_text).experiences[0]
        assert experience.id == "exp_001"
        assert experience.company == "Zoho Corporation"
        assert experience.role == "Software Developer"
        assert experience.employment_type == "Full Time"
        assert experience.duration == "May 2024 - Present"
        assert experience.location == "Chennai"
        assert experience.technologies == ["Java", "Spring Boot"]
        assert experience.domains == ["SOC Platforms"]

    def test_the_highlight_pool_is_kept_whole(self, kb_text):
        assert len(parse(kb_text).experiences[0].highlights) == 2

    def test_an_experience_without_highlights_raises(self, kb_text):
        broken = kb_text.replace(
            "- Designed Redis-based caching strategies for frequently accessed firewall rules.",
            "",
        ).replace(
            "- Built the MCP layer for an internal security platform, exposing REST APIs as model-invocable tools.",
            "",
        )
        with pytest.raises(MissingKnowledgeSection):
            parse(broken)

    def test_a_missing_required_field_raises(self, kb_text):
        with pytest.raises(MissingKnowledgeSection):
            parse(without_line(kb_text, "Employment Type:"))


class TestProjects:
    def test_every_field_is_read(self, kb_text):
        project = parse(kb_text).projects[0]
        assert project.id == "proj_001"
        assert project.name == "Resume Tailor"
        assert project.type == "Personal"
        assert project.repository == "https://github.com/Sundar0603/resume-tailor"

    def test_repository_is_optional(self, kb_text):
        assert parse(kb_text).projects[1].repository is None


class TestEducation:
    def test_every_field_is_read(self, kb_text):
        degree = parse(kb_text).education[0]
        assert degree.id == "edu_001"
        assert degree.institution == "Velammal Engineering College"
        assert degree.degree == "Bachelor of Engineering"
        assert degree.major == "Computer Science and Engineering"
        assert degree.cgpa == "9.18"


class TestSourceLineage:
    def test_everything_parsed_is_canonical(self, kb_text):
        kb = parse(kb_text)
        entities = (
            list(kb.skills)
            + list(kb.experiences)
            + list(kb.projects)
            + list(kb.education)
            + list(kb.summaries)
        )
        assert entities
        for entity in entities:
            assert entity.source is EntitySource.CANONICAL

    def test_nothing_parsed_is_generated(self, kb_text):
        kb = parse(kb_text)
        assert not [p for p in kb.projects if p.source is EntitySource.GENERATED]


class TestIdsAreDeclaredNotDerived:
    def test_a_block_without_an_id_raises(self, kb_text):
        with pytest.raises(MissingEntityId):
            parse(without_line(kb_text, "Id: proj_002"))

    def test_a_duplicate_id_raises(self, kb_text):
        with pytest.raises(DuplicateEntityId):
            parse(kb_text.replace("Id: proj_002", "Id: proj_001"))

    def test_a_wrong_prefix_raises(self, kb_text):
        with pytest.raises(MalformedEntityId):
            parse(kb_text.replace("Id: proj_002", "Id: exp_099"))

    def test_a_malformed_id_raises(self, kb_text):
        with pytest.raises(MalformedEntityId):
            parse(kb_text.replace("Id: proj_002", "Id: project two"))

    def test_ids_are_not_positional(self, kb_text):
        """
        The whole point of a declared id: renumber the file and the ids stay.

        ``ResumeParser`` would return proj_001/proj_002 here regardless of what
        the file said, because it numbers by position.
        """
        renamed = kb_text.replace("Id: proj_001", "Id: proj_042").replace(
            "Id: proj_002", "Id: proj_007"
        )
        assert [p.id for p in parse(renamed).projects] == ["proj_042", "proj_007"]


class TestStableIdsAcrossLoads:
    def test_two_parses_agree_on_every_id(self, kb_text):
        first, second = parse(kb_text), parse(kb_text)
        for attribute in ("skills", "experiences", "projects", "education", "summaries"):
            assert [e.id for e in getattr(first, attribute)] == [
                e.id for e in getattr(second, attribute)
            ]

    def test_two_parses_are_equal(self, kb_text):
        assert parse(kb_text) == parse(kb_text)

    def test_reordering_projects_does_not_change_their_ids(self, kb_text):
        """
        Moving a block must not rename it.

        This is the failure that makes positional ids unusable as canonical
        ones: yesterday's ``proj_002`` becomes today's ``proj_001``, and every
        recorded retrieval result silently means something else.
        """
        original = parse(kb_text)
        first = kb_text.index("## Project")
        second = kb_text.index("## Project", first + 1)
        end = kb_text.index("# Education")
        head, block_a, block_b = kb_text[:first], kb_text[first:second], kb_text[second:end]
        swapped = head + block_b + block_a + kb_text[end:]

        reordered = parse(swapped)
        assert [p.id for p in reordered.projects] == ["proj_002", "proj_001"]
        assert reordered.project("proj_001").name == original.project("proj_001").name
        assert reordered.project("proj_002").name == original.project("proj_002").name


class TestRequiredSections:
    @pytest.mark.parametrize(
        "heading",
        ["# Contact", "# Summaries", "# Skills", "# Work Experience", "# Projects", "# Education"],
    )
    def test_a_missing_section_raises(self, kb_text, heading):
        with pytest.raises(MissingKnowledgeSection):
            parse(kb_text.replace(heading, "# Something Else"))


class TestFileReading:
    def test_a_missing_file_raises(self):
        with pytest.raises(KnowledgeBaseNotFoundError):
            KnowledgeBaseParser().parse("knowledge/does-not-exist.md")

    def test_parse_and_parse_string_agree(self, tmp_path, kb_text):
        path = tmp_path / "kb.md"
        path.write_text(kb_text, encoding="utf-8")
        assert KnowledgeBaseParser().parse(str(path)) == parse(kb_text)


class TestAWrappedBulletIsLoud:
    """
    PROJECT_KNOWLEDGE §10c: ``get_list`` ends a list at the first non-bullet,
    non-blank line, so a wrapped bullet discards every later bullet in silence.
    The Knowledge Base is the one file a human edits directly and holds bullets
    long enough to invite a line break, so it refuses rather than truncates.
    """

    def test_a_wrapped_highlight_raises(self, kb_text):
        wrapped = kb_text.replace(
            "- Built the MCP layer for an internal security platform, exposing REST APIs as model-invocable tools.",
            "- Built the MCP layer for an internal security platform, exposing REST\n  APIs as model-invocable tools.",
            1,
        )
        with pytest.raises(WrappedBullet):
            parse(wrapped)

    def test_without_the_guard_the_loss_would_be_silent(self, kb_text):
        """The truncation this guard exists to prevent, measured on the helper."""
        from src.helpers._section_utils import get_list

        block = (
            "Highlights:\n\n"
            "- Built the MCP layer, exposing REST\n  APIs as tools.\n\n"
            "- Designed Redis-based caching strategies.\n"
        )
        assert len(get_list(block, "Highlights")) == 1

    def test_a_wrapped_technology_raises(self, kb_text):
        wrapped = kb_text.replace(
            "Technologies:\n\n- Java\n- Spring Boot",
            "Technologies:\n\n- Java\n  and friends\n- Spring Boot",
            1,
        )
        with pytest.raises(WrappedBullet):
            parse(wrapped)

    def test_an_unwrapped_document_still_parses(self, kb_text):
        assert len(parse(kb_text).experiences[0].highlights) == 2
