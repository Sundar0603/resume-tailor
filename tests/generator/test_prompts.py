"""
Tests for the Resume Generator prompt builders.

Prompts are pure functions. These tests pin what each one embeds, what it
deliberately leaves out, and that the mode rules actually differ.
"""

from src.generator import (
    build_experiences_prompt,
    build_projects_prompt,
    build_summary_prompt,
)
from src.planner.models import PlanningMode

from .conftest import make_job_analysis, make_plan, make_resume


def _summary_prompt(mode=PlanningMode.AGGRESSIVE, plan=None):
    return build_summary_prompt(
        make_resume(), make_job_analysis(), plan or make_plan(), mode
    )


def _experiences_prompt(mode=PlanningMode.AGGRESSIVE, plan=None):
    return build_experiences_prompt(
        make_resume(), make_job_analysis(), plan or make_plan(), mode
    )


def _projects_prompt(mode=PlanningMode.AGGRESSIVE, plan=None):
    return build_projects_prompt(
        make_resume(), make_job_analysis(), plan or make_plan(), mode
    )


class TestBraceDoubling:
    """The templates use str.format, so JSON braces must survive it."""

    def test_summary_schema_survives_formatting(self):
        assert '"summary":' in _summary_prompt()

    def test_experience_schema_survives_formatting(self):
        prompt = _experiences_prompt()
        assert '"experiences": [' in prompt
        assert '"experience_id":' in prompt

    def test_project_schema_survives_formatting(self):
        prompt = _projects_prompt()
        assert '"projects": [' in prompt
        assert '"project_id":' in prompt


class TestModeRules:
    def test_aggressive_permits_retitling(self):
        prompt = _summary_prompt(PlanningMode.AGGRESSIVE)
        assert "Mode: AGGRESSIVE" in prompt

    def test_strict_forbids_new_facts(self):
        prompt = _summary_prompt(PlanningMode.STRICT)
        assert "Mode: STRICT" in prompt
        assert "does not already appear" in prompt

    def test_modes_produce_different_prompts(self):
        assert _summary_prompt(PlanningMode.AGGRESSIVE) != _summary_prompt(
            PlanningMode.STRICT
        )

    def test_aggressive_forbids_seniority_inflation(self):
        # The one thing a retitle must never become.
        prompt = _experiences_prompt(PlanningMode.AGGRESSIVE)
        assert "Inflate seniority" in prompt

    def test_strict_pins_the_role(self):
        prompt = _experiences_prompt(PlanningMode.STRICT)
        assert "Change the role title" in prompt


class TestBudgets:
    def test_summary_states_the_word_budget(self):
        prompt = _summary_prompt()
        assert "20 to 120 words" in prompt

    def test_experience_states_the_highlight_budget(self):
        assert "at most 8 highlights" in _experiences_prompt()

    def test_project_states_the_highlight_budget(self):
        assert "at most 6 highlights" in _projects_prompt()


class TestTruncationOrdering:
    """
    Everything the Quality Gate can trim must be strongest-first, because it
    trims from the bottom to fit one page.
    """

    def test_experience_prompt_asks_for_strongest_first(self):
        prompt = _experiences_prompt()
        assert "Order the highlights strongest first" in prompt
        assert "trims this resume from the bottom" in prompt

    def test_project_prompt_asks_for_strongest_first(self):
        prompt = _projects_prompt()
        assert "Order the highlights strongest first" in prompt

    def test_aggressive_asks_for_a_quantified_outcome_per_section(self):
        prompt = _experiences_prompt(PlanningMode.AGGRESSIVE)
        assert "at least one quantified outcome" in prompt
        assert "must be believable" in prompt

    def test_strict_never_asks_for_a_quantified_outcome(self):
        # Strict forbids introducing any number not already in the source, so
        # asking for one would contradict the mode.
        prompt = _experiences_prompt(PlanningMode.STRICT)
        assert "at least one quantified outcome" not in prompt

    def test_believability_guardrails_are_stated(self):
        prompt = _experiences_prompt(PlanningMode.AGGRESSIVE)
        # The specific failure modes, not just "be realistic".
        assert "round and modest" in prompt
        assert "never invents a fact about the employer" in prompt

    def test_prompts_forbid_padding_to_the_limit(self):
        assert "Do not pad to the limit" in _experiences_prompt()
        assert "Do not pad to the limit" in _projects_prompt()


class TestPlanProjection:
    def _rewrite_plan(self):
        return make_plan(
            experience_plans=[
                {
                    "experience_id": "exp_001",
                    "action": "KEEP",
                    "priority": "LOW",
                    "rewrite_strategy": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Less relevant.",
                },
                {
                    "experience_id": "exp_002",
                    "action": "REWRITE",
                    "priority": "CRITICAL",
                    "rewrite_strategy": "Lead with payments and scale.",
                    "keywords_to_include": ["Python"],
                    "themes_to_emphasize": ["Backend"],
                    "reasoning": "Closest match to the target role.",
                },
            ]
        )

    def test_priority_renders_as_a_name_not_an_integer(self):
        # SectionPriority is an IntEnum: model_dump_json() would emit 1, which
        # tells a language model nothing.
        prompt = _experiences_prompt(plan=self._rewrite_plan())
        assert '"priority": "CRITICAL"' in prompt
        assert '"priority": 1' not in prompt

    def test_only_rewrite_experiences_are_included(self):
        prompt = _experiences_prompt(plan=self._rewrite_plan())
        plan_block = prompt.split("<plan>")[1].split("</plan>")[0]
        assert "exp_002" in plan_block
        assert "exp_001" not in plan_block

    def test_rewrite_strategy_and_themes_are_included(self):
        prompt = _experiences_prompt(plan=self._rewrite_plan())
        assert "Lead with payments and scale." in prompt
        assert "themes_to_emphasize" in prompt

    def test_generation_brief_reaches_the_project_prompt(self):
        plan = make_plan(
            project_plans=[
                {
                    "project_id": "proj_001",
                    "action": "KEEP",
                    "priority": "MEDIUM",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Still relevant.",
                },
                {
                    "project_id": "proj_002",
                    "action": "KEEP",
                    "priority": "MEDIUM",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Still relevant.",
                },
                {
                    "project_id": None,
                    "action": "GENERATE",
                    "priority": "HIGH",
                    "rewrite_strategy": None,
                    "generation_brief": "An event-driven microservices demo.",
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "The job wants event-driven experience.",
                },
            ]
        )
        assert "An event-driven microservices demo." in _projects_prompt(plan=plan)


class TestResumeProjection:
    def test_contact_details_never_reach_the_model(self):
        # Same rule as the planner: PII stays off the wire.
        for prompt in (_summary_prompt(), _experiences_prompt(), _projects_prompt()):
            assert "jane.doe@example.com" not in prompt
            assert "555-0100" not in prompt

    def test_education_is_not_sent(self):
        # It is immutable; sending it invites the model to rewrite it.
        assert "State University" not in _summary_prompt()

    def test_entity_ids_are_sent(self):
        prompt = _experiences_prompt()
        assert "exp_001" in prompt
        assert "exp_002" in prompt

    def test_job_analysis_is_embedded(self):
        assert "Globex" in _summary_prompt()
