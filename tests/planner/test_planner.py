"""
Transport and schema tests for the Resume Planner.

Covers:
    Valid cases   — a complete plan, strict mode, mode passed as a string
    Invalid cases — malformed JSON, empty response, unknown field, missing
                    reasoning, illegal action per section, provider failure,
                    unknown mode
    Behavior      — the planner never mutates the resume, the provider
                    receives PLANNER_NUM_CTX, strict forbids GENERATE while
                    aggressive allows it
"""

import copy
import json

import pytest

from src.planner import (
    InvalidPlannerJSON,
    InvalidPlannerResponse,
    PlannerError,
    PlanningModeViolation,
    ResumePlan,
    ResumePlanner,
    ResumePlanValidationError,
    UnknownPlanningMode,
)
from src.planner.models import PlanningMode
from src.planner.planner import PLANNER_NUM_CTX

from .conftest import (
    CapturingProvider,
    FailingProvider,
    FakeProvider,
    make_job_analysis,
    make_payload,
    make_resume,
)


def _planner(response: str) -> ResumePlanner:
    return ResumePlanner(provider=FakeProvider(response))


def _json(data: dict) -> str:
    return json.dumps(data)


class TestValidCases:

    def test_valid_plan(self):
        planner = _planner(_json(make_payload()))
        plan = planner.plan(make_resume(), make_job_analysis())

        assert isinstance(plan, ResumePlan)
        assert plan.mode == PlanningMode.AGGRESSIVE
        assert plan.summary_plan.action.value == "KEEP"
        assert {ep.experience_id for ep in plan.experience_plans} == {
            "exp_001",
            "exp_002",
        }
        assert {pp.project_id for pp in plan.project_plans} == {
            "proj_001",
            "proj_002",
        }
        assert {sp.category_id for sp in plan.skills_plans} == {
            "skill_001",
            "skill_002",
        }

    def test_mode_passed_as_lowercase_string(self):
        payload = make_payload()
        planner = _planner(_json(payload))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="strict")

        assert plan.mode == PlanningMode.STRICT

    def test_aggressive_allows_generate(self):
        payload = make_payload()
        payload["project_plans"].append(
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "A project demonstrating AWS deployment experience.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Job analysis calls for AWS experience not otherwise shown.",
            }
        )
        planner = _planner(_json(payload))
        plan = planner.plan(make_resume(), make_job_analysis(), mode="aggressive")

        generated = [pp for pp in plan.project_plans if pp.project_id is None]
        assert len(generated) == 1


class TestInvalidCases:

    def test_malformed_json(self):
        planner = _planner("not valid json {{{")
        with pytest.raises(InvalidPlannerJSON):
            planner.plan(make_resume(), make_job_analysis())

    def test_empty_response(self):
        planner = _planner("")
        with pytest.raises(InvalidPlannerResponse):
            planner.plan(make_resume(), make_job_analysis())

    def test_whitespace_only_response(self):
        planner = _planner("   \n  ")
        with pytest.raises(InvalidPlannerResponse):
            planner.plan(make_resume(), make_job_analysis())

    def test_unknown_field(self):
        payload = make_payload()
        payload["unknown_field"] = "should not be here"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_missing_reasoning(self):
        payload = make_payload()
        del payload["summary_plan"]["reasoning"]
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_illegal_action_on_summary(self):
        payload = make_payload()
        payload["summary_plan"]["action"] = "REMOVE"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_illegal_action_on_experience(self):
        payload = make_payload()
        payload["experience_plans"][0]["action"] = "GENERATE"
        planner = _planner(_json(payload))
        with pytest.raises(ResumePlanValidationError):
            planner.plan(make_resume(), make_job_analysis())

    def test_provider_raises_planner_error(self):
        exc = PlannerError("provider down")
        planner = ResumePlanner(provider=FailingProvider(exc))
        with pytest.raises(PlannerError):
            planner.plan(make_resume(), make_job_analysis())

    def test_provider_raises_unexpected_exception(self):
        exc = RuntimeError("network timeout")
        planner = ResumePlanner(provider=FailingProvider(exc))
        with pytest.raises(PlannerError):
            planner.plan(make_resume(), make_job_analysis())

    def test_unknown_mode_raises(self):
        planner = _planner(_json(make_payload()))
        with pytest.raises(UnknownPlanningMode):
            planner.plan(make_resume(), make_job_analysis(), mode="turbo")

    def test_strict_forbids_generate(self):
        payload = make_payload()
        payload["skills_plans"].append(
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "DevOps",
                "skills_to_add": ["Terraform"],
                "skills_to_remove": [],
                "reasoning": "Job analysis calls for DevOps skills not otherwise shown.",
            }
        )
        planner = _planner(_json(payload))
        with pytest.raises(PlanningModeViolation):
            planner.plan(make_resume(), make_job_analysis(), mode="strict")


class TestBehavior:

    def test_planner_does_not_mutate_resume(self):
        resume = make_resume()
        original = copy.deepcopy(resume)
        planner = _planner(_json(make_payload()))

        planner.plan(resume, make_job_analysis())

        assert resume == original

    def test_provider_receives_planner_num_ctx(self):
        provider = CapturingProvider(_json(make_payload()))
        planner = ResumePlanner(provider=provider)

        planner.plan(make_resume(), make_job_analysis())

        assert provider.options[0]["num_ctx"] == PLANNER_NUM_CTX

    def test_hallucinated_mode_is_overridden(self):
        payload = make_payload()
        payload["mode"] = "STRICT"
        planner = _planner(_json(payload))

        plan = planner.plan(make_resume(), make_job_analysis(), mode="aggressive")

        assert plan.mode == PlanningMode.AGGRESSIVE
