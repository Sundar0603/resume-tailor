"""
Parse -> Serialize -> Parse round trips.

Strict Pydantic equality holds for parser-produced resumes: their ids are
already dense and positional, and every source is CANONICAL, so a re-parse
reproduces them exactly.

It cannot hold for Generator output. ``source=GENERATED`` has no Markdown
representation, and ``mint_id`` uses ``highest + 1``, so a generated resume
can carry a sparse id sequence that ``assign_sequential_ids`` renumbers on
re-parse. Those cases compare semantically instead — content must match, and
only the runtime fields may differ.
"""

import pytest

from src.parser import ResumeParser
from src.parser.models import EntitySource
from src.renderer import MarkdownSerializer

from .conftest import (
    CANONICAL_RESUMES,
    make_generated_resume,
    make_resume,
    make_sparse_resume,
    semantically_equal,
)


class TestCanonicalResumes:
    @pytest.mark.parametrize("path", CANONICAL_RESUMES)
    def test_round_trip_is_exactly_equal(self, path):
        parser = ResumeParser()
        original = parser.parse(path)
        reparsed = parser.parse_string(MarkdownSerializer().serialize(original))
        assert reparsed == original

    @pytest.mark.parametrize("path", CANONICAL_RESUMES)
    def test_a_second_pass_is_byte_stable(self, path):
        parser, serializer = ResumeParser(), MarkdownSerializer()
        first = serializer.serialize(parser.parse(path))
        second = serializer.serialize(parser.parse_string(first))
        assert first == second

    @pytest.mark.parametrize("path", CANONICAL_RESUMES)
    def test_no_content_is_lost(self, path):
        parser = ResumeParser()
        original = parser.parse(path)
        reparsed = parser.parse_string(MarkdownSerializer().serialize(original))
        assert reparsed.total_skills() == original.total_skills()
        assert reparsed.total_highlights() == original.total_highlights()
        assert reparsed.word_count() == original.word_count()


class TestConstructedResumes:
    def test_a_full_resume_round_trips_exactly(self):
        original = make_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert reparsed == original

    def test_a_sparse_resume_round_trips_exactly(self):
        original = make_sparse_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert reparsed == original

    def test_a_resume_with_no_projects_round_trips(self):
        original = make_resume()
        original.projects = []
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert reparsed == original


class TestGeneratedResumes:
    def test_content_survives_but_runtime_fields_do_not(self):
        original = make_generated_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert semantically_equal(reparsed, original)
        assert reparsed != original

    def test_generated_source_reparses_as_canonical(self):
        original = make_generated_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert original.projects[0].source is EntitySource.GENERATED
        assert reparsed.projects[0].source is EntitySource.CANONICAL

    def test_sparse_ids_are_renumbered_positionally(self):
        original = make_generated_resume()
        reparsed = ResumeParser().parse_string(
            MarkdownSerializer().serialize(original)
        )
        assert [p.id for p in original.projects] == ["proj_002", "proj_005"]
        assert [p.id for p in reparsed.projects] == ["proj_001", "proj_002"]

    def test_a_generated_project_looks_like_any_other(self):
        markdown = MarkdownSerializer().serialize(make_generated_resume())
        blocks = markdown.split("## Project\n\n")[1:]
        assert len(blocks) == 2
        for block in blocks:
            assert "source" not in block
            assert "GENERATED" not in block


class TestParseString:
    def test_it_agrees_with_parsing_the_same_file(self):
        parser = ResumeParser()
        path = CANONICAL_RESUMES[0]
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
        assert parser.parse_string(raw) == parser.parse(path)

    def test_parse_still_raises_for_a_missing_file(self):
        with pytest.raises(FileNotFoundError):
            ResumeParser().parse("content/does_not_exist.md")
