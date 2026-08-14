"""
Tests for Resume Generator response normalisation.

Canonicalisation here is about tolerance, not determinism: at a non-zero
temperature the model produces small formatting variance that should not fail a
generation. Only shape and whitespace are touched — wording is never rewritten.
"""

from src.generator import (
    canonicalize_experiences,
    canonicalize_projects,
    canonicalize_summary,
)


class TestSummary:
    def test_collapses_whitespace(self):
        result = canonicalize_summary({"summary": "  Backend   engineer.  "})
        assert result["summary"] == "Backend engineer."

    def test_leaves_a_missing_summary_alone(self):
        # Absence is the schema's problem to report, not this module's.
        assert canonicalize_summary({}) == {"summary": None}


class TestExperiences:
    def test_null_list_becomes_empty(self):
        assert canonicalize_experiences({"experiences": None})["experiences"] == []

    def test_missing_key_becomes_empty(self):
        assert canonicalize_experiences({})["experiences"] == []

    def test_drops_blank_highlights(self):
        result = canonicalize_experiences(
            {
                "experiences": [
                    {
                        "experience_id": "exp_001",
                        "highlights": ["Shipped it.", "", "   ", "Owned it."],
                    }
                ]
            }
        )
        assert result["experiences"][0]["highlights"] == ["Shipped it.", "Owned it."]

    def test_strips_ids_and_roles(self):
        result = canonicalize_experiences(
            {"experiences": [{"experience_id": " exp_001 ", "role": " Engineer "}]}
        )
        entry = result["experiences"][0]
        assert entry["experience_id"] == "exp_001"
        assert entry["role"] == "Engineer"

    def test_deduplicates_case_insensitively_keeping_first_spelling(self):
        # A repeated skill inside one category is a validator error, and a
        # model listing "Python" twice is a formatting slip.
        result = canonicalize_experiences(
            {
                "experiences": [
                    {
                        "experience_id": "exp_001",
                        "technologies": ["Python", "python", "Go"],
                    }
                ]
            }
        )
        assert result["experiences"][0]["technologies"] == ["Python", "Go"]

    def test_non_string_entries_are_dropped(self):
        result = canonicalize_experiences(
            {"experiences": [{"experience_id": "exp_001", "domains": ["Backend", 42]}]}
        )
        assert result["experiences"][0]["domains"] == ["Backend"]

    def test_a_single_object_is_wrapped_in_a_list(self):
        result = canonicalize_experiences(
            {"experiences": {"experience_id": "exp_001"}}
        )
        assert len(result["experiences"]) == 1

    def test_does_not_mutate_the_input(self):
        payload = {"experiences": [{"experience_id": " exp_001 "}]}
        canonicalize_experiences(payload)
        assert payload["experiences"][0]["experience_id"] == " exp_001 "


class TestProjects:
    def test_null_list_becomes_empty(self):
        assert canonicalize_projects({"projects": None})["projects"] == []

    def test_preserves_a_null_project_id(self):
        # None means "this is a new project", and must survive intact.
        result = canonicalize_projects(
            {"projects": [{"project_id": None, "name": "Event Bus"}]}
        )
        assert result["projects"][0]["project_id"] is None

    def test_strips_name_and_type(self):
        result = canonicalize_projects(
            {"projects": [{"project_id": None, "name": " Event Bus ", "type": " OSS "}]}
        )
        entry = result["projects"][0]
        assert entry["name"] == "Event Bus"
        assert entry["type"] == "OSS"
