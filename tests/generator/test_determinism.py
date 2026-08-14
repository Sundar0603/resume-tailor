"""
Stability tests for the Resume Generator.

The Generator is deliberately **not** deterministic in its output — greedy
decoding produces flat, repetitive prose, so it samples. Two things around it
must still be stable, and this file pins both:

1. **Prompt text.** A prompt that varies between identical inputs makes every
   failure irreproducible.
2. **Schema field order.** Small local models reproduce a repeated JSON shape
   positionally. This is the failure that cost the Planner a whole build
   (``feedback/resume-planner-verdict.md`` §1.2) and the reason these
   assertions look pedantic.

There is deliberately no five-iteration output-identity test here. That would
assert the opposite of what the Generator is for.
"""

import re

from src.generator import (
    GENERATOR_MAX_TOKENS,
    GENERATOR_NUM_CTX,
    GENERATOR_TEMPERATURE,
    GENERATOR_TOP_K,
    GENERATOR_TOP_P,
    build_experiences_prompt,
    build_projects_prompt,
    build_summary_prompt,
    generator_options,
)
from src.planner.models import PlanningMode

from .conftest import make_job_analysis, make_plan, make_resume

_BUILDERS = (
    build_summary_prompt,
    build_experiences_prompt,
    build_projects_prompt,
)


class TestPromptStability:
    def test_identical_inputs_give_byte_identical_prompts(self):
        for builder in _BUILDERS:
            first = builder(
                make_resume(), make_job_analysis(), make_plan(), PlanningMode.STRICT
            )
            second = builder(
                make_resume(), make_job_analysis(), make_plan(), PlanningMode.STRICT
            )
            assert first == second

    def test_mode_changes_the_prompt(self):
        for builder in _BUILDERS:
            aggressive = builder(
                make_resume(),
                make_job_analysis(),
                make_plan(),
                PlanningMode.AGGRESSIVE,
            )
            strict = builder(
                make_resume(), make_job_analysis(), make_plan(), PlanningMode.STRICT
            )
            assert aggressive != strict


class TestSchemaFieldOrder:
    """
    The experience and project shapes share four fields. Those must appear in
    the same relative order in both, with the id field first and ``highlights``
    last, or a model that has just written one shape will carry its layout into
    the other.

    Reordering the schema fields in ``src/generator/prompts.py`` will fail
    these tests. That is the point.
    """

    _SHARED_TAIL = ("technologies", "domains", "highlights")

    def _schema_fields(self, prompt: str):
        """Return the field names of the schema block, in order."""
        block = prompt.split("Required JSON schema:")[1]
        return re.findall(r'"(\w+)":', block)

    def test_experience_shape_field_order(self):
        for mode in (PlanningMode.AGGRESSIVE, PlanningMode.STRICT):
            prompt = build_experiences_prompt(
                make_resume(), make_job_analysis(), make_plan(), mode
            )
            fields = self._schema_fields(prompt)
            assert fields == [
                "experiences",
                "experience_id",
                "role",
                "technologies",
                "domains",
                "highlights",
            ]

    def test_project_shape_field_order(self):
        for mode in (PlanningMode.AGGRESSIVE, PlanningMode.STRICT):
            prompt = build_projects_prompt(
                make_resume(), make_job_analysis(), make_plan(), mode
            )
            fields = self._schema_fields(prompt)
            assert fields == [
                "projects",
                "project_id",
                "name",
                "type",
                "technologies",
                "domains",
                "highlights",
            ]

    def test_shared_tail_is_identical_across_shapes(self):
        experience_fields = self._schema_fields(build_experiences_prompt(
                make_resume(),
                make_job_analysis(),
                make_plan(),
                PlanningMode.AGGRESSIVE,
            ))
        project_fields = self._schema_fields(build_projects_prompt(
                make_resume(),
                make_job_analysis(),
                make_plan(),
                PlanningMode.AGGRESSIVE,
            ))
        assert tuple(experience_fields[-3:]) == self._SHARED_TAIL
        assert tuple(project_fields[-3:]) == self._SHARED_TAIL

    def test_id_field_comes_first_in_both_shapes(self):
        experience_fields = self._schema_fields(build_experiences_prompt(
                make_resume(),
                make_job_analysis(),
                make_plan(),
                PlanningMode.AGGRESSIVE,
            ))
        project_fields = self._schema_fields(build_projects_prompt(
                make_resume(),
                make_job_analysis(),
                make_plan(),
                PlanningMode.AGGRESSIVE,
            ))
        assert experience_fields[1] == "experience_id"
        assert project_fields[1] == "project_id"


class TestSampling:
    def test_defaults_are_non_greedy(self):
        # Raising temperature while top_k stays at 1 changes nothing, so both
        # must move together.
        options = generator_options()
        assert options["temperature"] == GENERATOR_TEMPERATURE
        assert options["temperature"] > 0.0
        assert options["top_k"] == GENERATOR_TOP_K
        assert options["top_k"] > 1
        assert options["top_p"] == GENERATOR_TOP_P

    def test_context_and_budget_are_pinned(self):
        options = generator_options()
        assert options["num_ctx"] == GENERATOR_NUM_CTX
        assert options["max_tokens"] == GENERATOR_MAX_TOKENS

    def test_seed_is_retained(self):
        # A fixed seed keeps a given temperature reproducible, which costs
        # nothing in prose quality and makes failures debuggable.
        assert generator_options()["seed"] == 42

    def test_json_mode_stays_on(self):
        assert generator_options()["json_mode"] is True

    def test_temperature_is_overridable(self):
        assert generator_options(0.0)["temperature"] == 0.0
        # top_k stays widened even at temperature zero.
        assert generator_options(0.0)["top_k"] == GENERATOR_TOP_K

    def test_returns_an_independent_copy(self):
        first = generator_options()
        first["temperature"] = 99.0
        assert generator_options()["temperature"] == GENERATOR_TEMPERATURE

    def test_identical_on_every_call(self):
        assert generator_options() == generator_options()
