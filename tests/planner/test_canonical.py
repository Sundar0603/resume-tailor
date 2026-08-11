"""
Unit tests for planner canonicalization.

Covers action casing/aliases, priority name mapping (the IntEnum backstop),
null-equivalent collapsing, prose period handling, list dedupe/sort, and the
idempotence and non-mutation guarantees.
"""

import copy

from src.planner.canonical import canonicalize

from .conftest import make_payload


class TestActionCasing:

    def test_lowercase_action_is_uppercased(self):
        payload = make_payload()
        payload["summary_plan"]["action"] = "keep"
        result = canonicalize(payload)
        assert result["summary_plan"]["action"] == "KEEP"

    def test_action_alias_is_mapped(self):
        payload = make_payload()
        payload["project_plans"][1]["action"] = "delete"
        result = canonicalize(payload)
        assert result["project_plans"][1]["action"] == "REMOVE"


class TestPriority:

    def test_priority_name_maps_to_int(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = "critical"
        result = canonicalize(payload)
        assert result["summary_plan"]["priority"] == 1

    def test_priority_p_notation_maps_to_int(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = "P2"
        result = canonicalize(payload)
        assert result["summary_plan"]["priority"] == 2

    def test_priority_digit_string_maps_to_int(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = "3"
        result = canonicalize(payload)
        assert result["summary_plan"]["priority"] == 3

    def test_unrecognised_priority_passes_through(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = "SUPER_URGENT"
        result = canonicalize(payload)
        assert result["summary_plan"]["priority"] == "SUPER_URGENT"


class TestNullableScalars:

    def test_null_equivalent_category_id_becomes_none(self):
        payload = make_payload()
        payload["skills_plans"][0]["new_category_name"] = "N/A"
        result = canonicalize(payload)
        assert result["skills_plans"][0]["new_category_name"] is None


class TestProseFields:

    def test_reasoning_keeps_terminal_period(self):
        payload = make_payload()
        payload["summary_plan"]["reasoning"] = "  Already strong.  "
        result = canonicalize(payload)
        assert result["summary_plan"]["reasoning"] == "Already strong."

    def test_rewrite_strategy_keeps_terminal_period(self):
        payload = make_payload()
        payload["experience_plans"][1]["rewrite_strategy"] = "Emphasize scale."
        result = canonicalize(payload)
        assert result["experience_plans"][1]["rewrite_strategy"] == "Emphasize scale."


class TestListFields:

    def test_keywords_deduped_case_insensitively_and_sorted(self):
        payload = make_payload()
        payload["summary_plan"]["keywords_to_include"] = ["python", "Python", "AWS"]
        result = canonicalize(payload)
        assert result["summary_plan"]["keywords_to_include"] == ["AWS", "python"]


class TestOrdering:

    def test_generate_entries_sort_last(self):
        payload = make_payload()
        payload["project_plans"].insert(
            0,
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "A new project.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Filling a gap.",
            },
        )
        result = canonicalize(payload)
        ids = [pp["project_id"] for pp in result["project_plans"]]
        assert ids[-1] is None
        assert ids[:-1] == sorted(ids[:-1])


class TestIdempotenceAndMutation:

    def test_idempotent(self):
        payload = make_payload()
        once = canonicalize(payload)
        twice = canonicalize(once)
        assert once == twice

    def test_does_not_mutate_input(self):
        payload = make_payload()
        original = copy.deepcopy(payload)
        canonicalize(payload)
        assert payload == original

    def test_non_dict_passthrough(self):
        assert canonicalize([1, 2, 3]) == [1, 2, 3]
