"""
Determinism tests for the Resume Planner.

The planner emits *decisions*, not prose, so the same resume and job analysis
must always yield the same ResumePlan. That guarantee rests on the same three
mechanisms the analyzer relies on, each covered here:

* sampling — the provider is always called with pinned parameters
* extraction — response wrappers never change the parsed plan
* canonicalization — equivalent payloads collapse to one identical plan

A fourth concern is specific to the planner: **schema field order in the
prompt**. The planner asks for four different entry shapes in one JSON object,
and a small local model reproduces them positionally. When ``reasoning`` sat in
a different slot in ``skills_plans`` than in the other three shapes, the model
carried the skills layout into ``project_plans`` — writing
``new_category_name`` into the slot where ``reasoning`` belonged, which both
dropped a required field and added a forbidden one. :class:`TestSchemaFieldOrder`
pins the invariant that prevented it.

No network access required.
"""

import json
import re
from typing import Any, Dict, List, Optional

from src.analyzer.sampling import DETERMINISTIC_SEED
from src.analyzer.provider import LLMProvider
from src.planner import ResumePlan, ResumePlanner
from src.planner.canonical import canonicalize
from src.planner.models import PlanningMode
from src.planner.planner import (
    PLANNER_MAX_TOKENS,
    PLANNER_NUM_CTX,
    planner_options,
)
from src.planner.prompts import build_planning_prompt

from .conftest import make_job_analysis, make_payload, make_resume


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    """Returns the next pre-scripted response on each successive call."""

    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self._call = 0
        self.prompts: List[str] = []
        self.options: List[Optional[Dict[str, Any]]] = []

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.prompts.append(prompt)
        self.options.append(options)
        response = self._responses[self._call % len(self._responses)]
        self._call += 1
        return response


# ---------------------------------------------------------------------------
# Payload variants — five plausible spellings of one identical plan
# ---------------------------------------------------------------------------


def _iteration_variants() -> List[str]:
    """
    Five responses a model might plausibly return across separate calls for
    the same resume and job analysis. Every one must canonicalize to the same
    ResumePlan.

    Terminal periods on prose fields are deliberately left alone: the planner
    keeps them (they are sentences), so varying them would be a real
    difference, not noise.
    """
    # 1. Already canonical.
    first = json.dumps(make_payload())

    # 2. Set-like lists in a different order.
    shuffled = make_payload()
    shuffled["experience_plans"][1]["keywords_to_include"] = ["AWS", "Python"]
    shuffled["experience_plans"][1]["themes_to_emphasize"] = ["scale", "ownership"]
    second = json.dumps(shuffled)

    # 3. Duplicates and inconsistent casing in set-like lists.
    duplicated = make_payload()
    duplicated["experience_plans"][1]["keywords_to_include"] = [
        "Python",
        "python",
        "AWS",
        "aws",
    ]
    duplicated["experience_plans"][1]["themes_to_emphasize"] = [
        "ownership",
        "Ownership",
        "scale",
    ]
    third = json.dumps(duplicated)

    # 4. Whitespace noise, bullet prefixes, lowercase actions, priority aliases.
    noisy = make_payload()
    noisy["summary_plan"]["action"] = "keep"
    noisy["summary_plan"]["priority"] = "P3"
    noisy["experience_plans"][1]["action"] = "rewrite"
    noisy["experience_plans"][1]["priority"] = 1
    noisy["experience_plans"][1]["keywords_to_include"] = ["  Python  ", "- AWS"]
    noisy["experience_plans"][1]["themes_to_emphasize"] = ["ownership.", "  scale"]
    fourth = json.dumps(noisy)

    # 5. Wrapped in a markdown fence with surrounding prose.
    fifth = (
        "Here is the plan:\n```json\n" + json.dumps(make_payload()) + "\n```\nLet me know."
    )

    return [first, second, third, fourth, fifth]


def _plan(response: str, mode: PlanningMode = PlanningMode.AGGRESSIVE) -> ResumePlan:
    planner = ResumePlanner(provider=ScriptedProvider([response]))
    return planner.plan(make_resume(), make_job_analysis(), mode=mode)


# ---------------------------------------------------------------------------
# The headline guarantee
# ---------------------------------------------------------------------------


class TestFiveIterations:
    """Five plausible spellings of one plan collapse to one identical value."""

    def test_all_iterations_agree(self):
        provider = ScriptedProvider(_iteration_variants())
        planner = ResumePlanner(provider=provider)
        resume = make_resume()
        analysis = make_job_analysis()

        results = [planner.plan(resume, analysis) for _ in range(5)]

        assert len(results) == 5
        first = results[0]
        for index, result in enumerate(results[1:], start=2):
            assert result == first, f"iteration {index} differs from iteration 1"

    def test_serialized_form_is_identical(self):
        provider = ScriptedProvider(_iteration_variants())
        planner = ResumePlanner(provider=provider)
        resume = make_resume()
        analysis = make_job_analysis()

        dumps = {
            json.dumps(planner.plan(resume, analysis).model_dump(), sort_keys=True, default=str)
            for _ in range(5)
        }

        assert len(dumps) == 1

    def test_repeated_planning_does_not_drift(self):
        provider = ScriptedProvider([json.dumps(make_payload())])
        planner = ResumePlanner(provider=provider)
        resume = make_resume()
        analysis = make_job_analysis()

        plans = [planner.plan(resume, analysis) for _ in range(5)]

        assert all(plan == plans[0] for plan in plans)


# ---------------------------------------------------------------------------
# Schema field order — the regression guard
# ---------------------------------------------------------------------------


class TestSchemaFieldOrder:
    """
    ``reasoning`` must sit immediately after ``priority`` in *every* entry
    shape.

    A small local model reproduces the schema positionally. If one shape puts a
    different field in that slot, the model carries the wrong layout across
    shapes and emits an entry that is missing ``reasoning`` and carrying a
    foreign key. Keeping the slot uniform is what stops it.
    """

    #: Every entry shape in the prompt's schema skeleton.
    BLOCKS = ("summary_plan", "skills_plans", "experience_plans", "project_plans")

    @staticmethod
    def _keys_in_order(text: str) -> List[str]:
        return re.findall(r'"(\w+)":', text)

    def _block(self, prompt: str, name: str) -> str:
        """Return the schema text for one entry shape."""
        start = prompt.index(f'"{name}":')
        following = [
            prompt.index(f'"{other}":')
            for other in self.BLOCKS
            if other != name and prompt.index(f'"{other}":') > start
        ]
        end = min(following) if following else len(prompt)
        return prompt[start:end]

    def test_reasoning_follows_priority_in_every_block(self):
        prompt = build_planning_prompt(
            make_resume(), make_job_analysis(), PlanningMode.AGGRESSIVE
        )

        for block in self.BLOCKS:
            keys = self._keys_in_order(self._block(prompt, block))
            assert "priority" in keys, block
            assert "reasoning" in keys, block
            position = keys.index("priority")
            assert keys[position + 1] == "reasoning", (
                f"{block}: expected 'reasoning' immediately after 'priority', "
                f"got {keys[position + 1]!r} (order: {keys})"
            )

    def test_holds_in_strict_mode_too(self):
        prompt = build_planning_prompt(
            make_resume(), make_job_analysis(), PlanningMode.STRICT
        )

        for block in self.BLOCKS:
            keys = self._keys_in_order(self._block(prompt, block))
            position = keys.index("priority")
            assert keys[position + 1] == "reasoning", block

    def test_generate_only_fields_do_not_precede_reasoning(self):
        """
        ``new_category_name`` and ``generation_brief`` are the two fields that
        are legal in one shape and forbidden in another. Neither may occupy a
        slot before ``reasoning``, or the positional confusion returns.
        """
        prompt = build_planning_prompt(
            make_resume(), make_job_analysis(), PlanningMode.AGGRESSIVE
        )

        for block in self.BLOCKS:
            keys = self._keys_in_order(self._block(prompt, block))
            reasoning_at = keys.index("reasoning")
            for field in ("new_category_name", "generation_brief"):
                if field in keys:
                    assert keys.index(field) > reasoning_at, (
                        f"{block}: {field!r} precedes 'reasoning'"
                    )


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


class TestSampling:
    def test_planner_options_are_greedy_and_pinned(self):
        options = planner_options()

        assert options["temperature"] == 0.0
        assert options["top_k"] == 1
        assert options["top_p"] == 1.0
        assert options["seed"] == DETERMINISTIC_SEED
        assert options["json_mode"] is True

    def test_planner_widens_the_context_window(self):
        options = planner_options()

        assert options["num_ctx"] == PLANNER_NUM_CTX
        assert options["max_tokens"] == PLANNER_MAX_TOKENS
        # The planner prompt carries a resume, an analysis, and a ~90-line
        # schema; the analyzer default would truncate it.
        assert PLANNER_NUM_CTX > 8192

    def test_options_are_identical_on_every_call(self):
        provider = ScriptedProvider([json.dumps(make_payload())])
        planner = ResumePlanner(provider=provider)
        resume = make_resume()
        analysis = make_job_analysis()

        for _ in range(5):
            planner.plan(resume, analysis)

        assert all(options == provider.options[0] for options in provider.options)

    def test_helper_returns_an_independent_copy(self):
        first = planner_options()
        first["temperature"] = 1.0

        assert planner_options()["temperature"] == 0.0


# ---------------------------------------------------------------------------
# Prompt stability
# ---------------------------------------------------------------------------


class TestPromptStability:
    def test_prompt_is_byte_stable_across_builds(self):
        resume = make_resume()
        analysis = make_job_analysis()

        prompts = {
            build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
            for _ in range(5)
        }

        assert len(prompts) == 1

    def test_planner_sends_the_built_prompt(self):
        provider = ScriptedProvider([json.dumps(make_payload())])
        resume = make_resume()
        analysis = make_job_analysis()

        ResumePlanner(provider=provider).plan(resume, analysis, mode=PlanningMode.STRICT)

        assert provider.prompts[0] == build_planning_prompt(
            resume, analysis, PlanningMode.STRICT
        )

    def test_equal_resumes_produce_equal_prompts(self):
        left = build_planning_prompt(
            make_resume(), make_job_analysis(), PlanningMode.AGGRESSIVE
        )
        right = build_planning_prompt(
            make_resume(), make_job_analysis(), PlanningMode.AGGRESSIVE
        )

        assert left == right


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TestExtraction:
    WRAPPERS = (
        "{body}",
        "```json\n{body}\n```",
        "```\n{body}\n```",
        "Here is the plan:\n{body}",
        "{body}\n\nLet me know if you need anything else.",
        "  \n{body}\n  ",
    )

    def test_wrapped_responses_produce_the_same_plan(self):
        body = json.dumps(make_payload())
        baseline = _plan(body)

        for wrapper in self.WRAPPERS:
            assert _plan(wrapper.format(body=body)) == baseline, wrapper

    def test_braces_inside_strings_do_not_truncate_the_object(self):
        payload = make_payload()
        payload["summary_plan"]["reasoning"] = "Mentions {placeholders} in prose."

        plan = _plan(json.dumps(payload))

        assert plan.summary_plan.reasoning == "Mentions {placeholders} in prose."


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


class TestCanonicalization:
    def test_every_variant_canonicalizes_identically(self):
        from src.analyzer._json_extract import extract_json_object

        canonical = [
            canonicalize(json.loads(extract_json_object(variant)))
            for variant in _iteration_variants()
        ]

        first = json.dumps(canonical[0], sort_keys=True)
        for index, payload in enumerate(canonical[1:], start=2):
            assert json.dumps(payload, sort_keys=True) == first, f"variant {index}"

    def test_is_idempotent_on_every_variant(self):
        from src.analyzer._json_extract import extract_json_object

        for index, variant in enumerate(_iteration_variants(), start=1):
            once = canonicalize(json.loads(extract_json_object(variant)))
            assert canonicalize(once) == once, f"variant {index}"
