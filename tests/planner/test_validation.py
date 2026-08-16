"""
Semantic validation tests for the Resume Planner.

Covers the plan-vs-resume consistency ruleset: unknown ids, immutable
sections, missing priority, duplicate ids, missing plan entries, GENERATE
id/brief pairing, and the soft-drop behavior for a bad skill removal.
"""

import json

import pytest
from pydantic import ValidationError

from src.planner import (
    DuplicatePlanEntry,
    ImmutableSectionViolation,
    MissingPlanEntry,
    PlanAction,
    PlanConsistencyError,
    PlanningModeViolation,
    ResumePlanValidationError,
    ResumePlanner,
    SectionPriority,
    SkillCategoryPlan,
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


class TestSkillCategoryNaming:
    """
    Rules added in task 012, when the Resume Generator became the consumer.

    The generator applies skill categories in pure Python — no LLM call — so
    whatever the planner emits here reaches the rendered resume verbatim.
    """

    def _generated_category(self, **overrides):
        entry = {
            "category_id": None,
            "action": "GENERATE",
            "priority": "HIGH",
            "reasoning": "The job needs container tooling.",
            "new_category_name": "Container & Orchestration",
            "skills_to_add": ["Docker", "Kubernetes"],
            "skills_to_remove": [],
        }
        entry.update(overrides)
        return entry

    def test_generate_without_skills_rejected(self):
        # The validator only warns about an empty category, so an unenforced
        # empty skills_to_add would ship a heading with nothing under it.
        payload = make_payload()
        payload["skills_plans"].append(self._generated_category(skills_to_add=[]))
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_generate_with_skills_accepted(self):
        payload = make_payload()
        payload["skills_plans"].append(self._generated_category())
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        generated = [sp for sp in plan.skills_plans if sp.category_id is None]
        assert len(generated) == 1
        assert generated[0].new_category_name == "Container & Orchestration"
        assert generated[0].skills_to_add == ["Docker", "Kubernetes"]

    def test_rewrite_may_rename_category(self):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REWRITE"
        payload["skills_plans"][0]["new_category_name"] = "Backend & Distributed Systems"
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        renamed = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert renamed.new_category_name == "Backend & Distributed Systems"

    def test_rewrite_rename_is_optional(self):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REWRITE"
        payload["skills_plans"][0]["new_category_name"] = None
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        kept = next(sp for sp in plan.skills_plans if sp.category_id == "skill_001")
        assert kept.new_category_name is None

    def test_rewrite_blank_rename_becomes_no_rename(self):
        # canonicalize() already folds "", "   " and "null" to None for the
        # nullable scalar fields, so a blank rename means "keep the name"
        # rather than failing the whole plan.
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REWRITE"
        payload["skills_plans"][0]["new_category_name"] = "   "
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        kept = next(sp for sp in plan.skills_plans if sp.category_id == "skill_001")
        assert kept.new_category_name is None

    def test_blank_rename_rejected_at_model_level(self):
        # Constructed directly, bypassing canonicalize().
        with pytest.raises(ValidationError):
            SkillCategoryPlan(
                category_id="skill_001",
                action=PlanAction.REWRITE,
                priority=SectionPriority.HIGH,
                new_category_name="   ",
                reasoning="why",
            )

    def test_keep_may_not_rename(self):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "KEEP"
        payload["skills_plans"][0]["new_category_name"] = "Something Else"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_remove_may_not_rename(self):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REMOVE"
        payload["skills_plans"][0]["new_category_name"] = "Something Else"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())


class TestStrictSkillAdditions:
    """
    Rule 26, added in task 012 after a live run caught it.

    Strict mode forbids GENERATE, but nothing stopped a REWRITE from smuggling
    a brand-new skill in through ``skills_to_add`` — and the Resume Generator
    applies skill plans verbatim in pure Python, so it reached the resume as a
    claim the candidate never made. Dropped and reported, matching how rule 21
    handles an impossible removal.
    """

    def _plan_adding(self, *skills):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REWRITE"
        payload["skills_plans"][0]["skills_to_add"] = list(skills)
        return payload

    def test_strict_drops_an_unsupported_skill(self):
        planner = _planner(_json(self._plan_adding("Kubernetes")))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="strict")

        rewritten = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert rewritten.skills_to_add == []

    def test_strict_reports_the_dropped_skill(self):
        planner = _planner(_json(self._plan_adding("Kubernetes")))
        planner.plan(make_resume(), make_job_analysis(), mode="strict")
        assert any("Kubernetes" in note for note in planner.last_discarded)

    def test_strict_keeps_a_skill_shown_elsewhere_in_the_resume(self):
        # Promoting a technology that only appears on an experience into the
        # skills section is reorganizing, which strict mode allows.
        planner = _planner(_json(self._plan_adding("Python")))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="strict")

        rewritten = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert rewritten.skills_to_add == ["Python"]

    def test_strict_filters_only_the_unsupported_entries(self):
        planner = _planner(_json(self._plan_adding("Python", "Kubernetes")))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="strict")

        rewritten = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert rewritten.skills_to_add == ["Python"]

    def test_aggressive_keeps_an_unsupported_skill(self):
        planner = _planner(_json(self._plan_adding("Kubernetes")))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="aggressive")

        rewritten = next(
            sp for sp in plan.skills_plans if sp.category_id == "skill_001"
        )
        assert rewritten.skills_to_add == ["Kubernetes"]
        assert planner.last_discarded == []

    def test_strict_generate_still_reports_the_mode_violation(self):
        # The filter must not empty a GENERATE entry's skills and trip the
        # non-empty rule instead of the clearer mode violation.
        payload = make_payload()
        payload["skills_plans"].append(
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Orchestration",
                "skills_to_add": ["Kubernetes"],
                "skills_to_remove": [],
                "reasoning": "The job needs orchestration.",
            }
        )
        planner = _planner(_json(payload))
        with pytest.raises(PlanningModeViolation):
            planner.plan(make_resume(), make_job_analysis(), mode="strict")


class TestActivityPhrasesAreNotSkills:
    """
    Rule 27, added in task 012 after a live run produced skill categories full
    of job-description prose.

    The planner prompt forbids this and lists the exact offending strings as
    negative examples; qwen3.6 emitted them anyway. The Resume Generator
    applies skill plans verbatim in pure Python, so they reached the resume.
    """

    def _plan_adding(self, *skills):
        payload = make_payload()
        payload["skills_plans"][0]["action"] = "REWRITE"
        payload["skills_plans"][0]["skills_to_add"] = list(skills)
        return payload

    def _added(self, plan):
        entry = next(sp for sp in plan.skills_plans if sp.category_id == "skill_001")
        return entry.skills_to_add

    @pytest.mark.parametrize(
        "phrase",
        [
            "Interoperability Strategies",
            "Defect Handling",
            "Code Quality",
            "Optimization of Coding",
            "API Versioning",
            "Quality Assurance Processes",
            "Application Software Development Lifecycle",
            "Broad Acceptance Criteria",
            "System Maintenance",
            "API Functionality",
            "SDLC",
        ],
    )
    def test_activity_phrases_are_dropped(self, phrase):
        planner = _planner(_json(self._plan_adding("Python", phrase)))
        plan = planner.plan(make_resume(), make_job_analysis())
        assert self._added(plan) == ["Python"]

    @pytest.mark.parametrize(
        "skill",
        [
            "Kubernetes",
            "Spring Boot",
            "PostgreSQL",
            "System Design",
            "Cloud Architecture",
            "Unit Testing",
            "Web Services",
            "OAuth 2.0",
            "Internet of Things",
        ],
    )
    def test_real_skills_survive(self, skill):
        planner = _planner(_json(self._plan_adding(skill)))
        plan = planner.plan(make_resume(), make_job_analysis())
        assert self._added(plan) == [skill]

    def test_the_drop_is_reported(self):
        planner = _planner(_json(self._plan_adding("Interoperability Strategies")))
        planner.plan(make_resume(), make_job_analysis())
        assert any(
            "Interoperability Strategies" in note for note in planner.last_discarded
        )

    def test_existing_resume_skills_are_never_touched(self):
        # The candidate's own wording is theirs. Only additions are filtered.
        resume = make_resume()
        resume.skills[0].skills = ["Python", "Query Optimization"]
        planner = _planner(_json(make_payload()))

        plan = planner.plan(resume, make_job_analysis())

        assert resume.skills[0].skills == ["Python", "Query Optimization"]
        assert planner.last_discarded == []
        assert plan.skills_plans[0].skills_to_add == []

    def test_a_generate_category_is_never_emptied(self):
        # Emptying it would breach rule 24 and report a confusing schema error
        # instead of this one.
        payload = make_payload()
        payload["skills_plans"].append(
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Practices",
                "skills_to_add": ["Defect Handling", "Code Quality"],
                "skills_to_remove": [],
                "reasoning": "The job stresses process maturity.",
            }
        )
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        # canonicalize() sorts skill lists, so compare as a set.
        generated = next(sp for sp in plan.skills_plans if sp.category_id is None)
        assert set(generated.skills_to_add) == {"Defect Handling", "Code Quality"}

    def test_a_generate_category_is_partially_filtered(self):
        payload = make_payload()
        payload["skills_plans"].append(
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Container & Orchestration",
                "skills_to_add": ["Kubernetes", "Defect Handling"],
                "skills_to_remove": [],
                "reasoning": "The job needs container tooling.",
            }
        )
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis())

        generated = next(sp for sp in plan.skills_plans if sp.category_id is None)
        assert generated.skills_to_add == ["Kubernetes"]


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
