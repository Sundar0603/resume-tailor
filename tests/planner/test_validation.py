"""
Semantic validation tests for the Resume Planner.

Covers the plan-vs-resume consistency ruleset: unknown ids, immutable
sections, missing priority, duplicate ids, missing plan entries, GENERATE
id/brief pairing, and the soft-drop behavior for a bad skill removal.
"""

import json

import pytest

from src.planner import (
    DuplicatePlanEntry,
    ImmutableSectionViolation,
    MissingPlanEntry,
    PlanConsistencyError,
    ResumePlanValidationError,
    ResumePlanner,
    UnknownEntityReference,
)

from .conftest import FakeProvider, make_job_analysis, make_payload, make_resume


def _planner(response: str) -> ResumePlanner:
    return ResumePlanner(provider=FakeProvider(response))


def _json(data: dict) -> str:
    return json.dumps(data)


class TestUnknownEntityReference:

    def test_unknown_experience_id(self):
        payload = make_payload()
        payload["experience_plans"][0]["experience_id"] = "exp_999"
        planner = _planner(_json(payload))
        with pytest.raises(UnknownEntityReference):
            planner.plan(make_resume(), make_job_analysis())

    def test_unknown_project_id(self):
        payload = make_payload()
        payload["project_plans"][0]["project_id"] = "proj_999"
        planner = _planner(_json(payload))
        with pytest.raises(UnknownEntityReference):
            planner.plan(make_resume(), make_job_analysis())

    def test_unknown_category_id(self):
        payload = make_payload()
        payload["skills_plans"][0]["category_id"] = "skill_999"
        planner = _planner(_json(payload))
        with pytest.raises(UnknownEntityReference):
            planner.plan(make_resume(), make_job_analysis())


class TestImmutableSections:

    def test_education_plan_rejected(self):
        payload = make_payload()
        payload["education_plan"] = {"action": "KEEP"}
        planner = _planner(_json(payload))
        with pytest.raises(ImmutableSectionViolation):
            planner.plan(make_resume(), make_job_analysis())

    def test_contact_plan_rejected(self):
        payload = make_payload()
        payload["contact_plan"] = {"action": "KEEP"}
        planner = _planner(_json(payload))
        with pytest.raises(ImmutableSectionViolation):
            planner.plan(make_resume(), make_job_analysis())

    def test_metadata_rejected(self):
        payload = make_payload()
        payload["metadata"] = {"version": "2.0"}
        planner = _planner(_json(payload))
        with pytest.raises(ImmutableSectionViolation):
            planner.plan(make_resume(), make_job_analysis())


class TestPriority:

    def test_missing_priority(self):
        payload = make_payload()
        del payload["summary_plan"]["priority"]
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_null_priority(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = None
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_unrecognised_priority(self):
        payload = make_payload()
        payload["summary_plan"]["priority"] = "SUPER_URGENT"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())


class TestDuplicateIds:

    def test_duplicate_experience_id(self):
        payload = make_payload()
        payload["experience_plans"][1]["experience_id"] = "exp_001"
        planner = _planner(_json(payload))
        with pytest.raises(DuplicatePlanEntry):
            planner.plan(make_resume(), make_job_analysis())

    def test_duplicate_project_id(self):
        payload = make_payload()
        payload["project_plans"][1]["project_id"] = "proj_001"
        planner = _planner(_json(payload))
        with pytest.raises(DuplicatePlanEntry):
            planner.plan(make_resume(), make_job_analysis())

    def test_duplicate_category_id(self):
        payload = make_payload()
        payload["skills_plans"][1]["category_id"] = "skill_001"
        planner = _planner(_json(payload))
        with pytest.raises(DuplicatePlanEntry):
            planner.plan(make_resume(), make_job_analysis())


class TestMissingPlanEntry:

    def test_missing_experience_entry(self):
        payload = make_payload()
        del payload["experience_plans"][1]
        planner = _planner(_json(payload))
        with pytest.raises(MissingPlanEntry):
            planner.plan(make_resume(), make_job_analysis())

    def test_missing_project_entry(self):
        payload = make_payload()
        del payload["project_plans"][1]
        planner = _planner(_json(payload))
        with pytest.raises(MissingPlanEntry):
            planner.plan(make_resume(), make_job_analysis())

    def test_missing_category_entry(self):
        payload = make_payload()
        del payload["skills_plans"][1]
        planner = _planner(_json(payload))
        with pytest.raises(MissingPlanEntry):
            planner.plan(make_resume(), make_job_analysis())

    def test_generate_entries_excluded_from_covering_set(self):
        # A GENERATE entry has no id, so it can never satisfy the
        # requirement that every existing resume entity has a plan entry.
        payload = make_payload()
        del payload["project_plans"][1]
        payload["project_plans"].append(
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "A new project.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Filling a gap.",
            }
        )
        planner = _planner(_json(payload))
        with pytest.raises(MissingPlanEntry):
            planner.plan(make_resume(), make_job_analysis())


class TestGeneratePairing:

    def test_generate_with_non_null_id_rejected(self):
        payload = make_payload()
        payload["project_plans"].append(
            {
                "project_id": "proj_001",
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "A new project.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Filling a gap.",
            }
        )
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_generate_missing_brief_rejected(self):
        payload = make_payload()
        payload["project_plans"].append(
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Filling a gap.",
            }
        )
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_non_generate_with_null_id_rejected(self):
        payload = make_payload()
        payload["project_plans"][0]["project_id"] = None
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())


class TestRewriteStrategy:

    def test_rewrite_without_strategy_rejected(self):
        payload = make_payload()
        payload["experience_plans"][1]["action"] = "REWRITE"
        payload["experience_plans"][1]["rewrite_strategy"] = None
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_keep_with_strategy_rejected(self):
        payload = make_payload()
        payload["experience_plans"][0]["rewrite_strategy"] = "Do something."
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())


class TestSkillRemoval:

    def test_bad_skill_removal_is_dropped_not_failed(self):
        payload = make_payload()
        payload["skills_plans"][0]["skills_to_remove"] = ["Rust"]
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        skill_001_plan = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert skill_001_plan.skills_to_remove == []
        assert len(planner.last_discarded) == 1
        assert "Rust" in planner.last_discarded[0]

    def test_valid_skill_removal_is_kept(self):
        payload = make_payload()
        payload["skills_plans"][0]["skills_to_remove"] = ["Python"]
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        skill_001_plan = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert skill_001_plan.skills_to_remove == ["Python"]
        assert planner.last_discarded == []

    def test_skill_in_both_add_and_remove_raises(self):
        payload = make_payload()
        payload["skills_plans"][0]["skills_to_add"] = ["Rust"]
        payload["skills_plans"][0]["skills_to_remove"] = ["Rust"]
        planner = _planner(_json(payload))
        with pytest.raises(PlanConsistencyError):
            planner.plan(make_resume(), make_job_analysis())
