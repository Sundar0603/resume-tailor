"""
Determinism tests for the Job Description Analyzer.

The analyzer must return the same JobAnalysis every time it is given the same
job description. That guarantee rests on three mechanisms, each covered here:

    sampling        — the provider is always called with pinned parameters
    extraction      — response wrappers never change the parsed result
    canonicalization — equivalent payloads collapse to one identical value

No network access is required. The offline proof works by feeding the
analyzer several responses that a model might plausibly return across
separate calls — reordered lists, case differences, duplicated entries,
inconsistent punctuation, a stray code fence — and asserting that every one
of them produces the *same* JobAnalysis.

A live check against a real provider lives in verify_determinism.py.
"""

import json
from typing import Any, Dict, List, Optional

import pytest

from src.analyzer import (
    DETERMINISTIC_OPTIONS,
    JDAnalyzer,
    JobAnalysis,
    LLMProvider,
    canonicalize,
    deterministic_options,
)
from src.analyzer._json_extract import extract_json_object
from src.analyzer.canonical import PROSE_FIELDS, SET_LIKE_FIELDS
from src.analyzer.prompts import build_analysis_prompt
from src.analyzer.sampling import DETERMINISTIC_SEED

JOB_DESCRIPTION = "Senior Backend Engineer at Acme Corp. Python and PostgreSQL required."


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    """Returns a different pre-scripted response on each successive call."""

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
# Payload variants — the same analysis as five different model responses
# ---------------------------------------------------------------------------


def _canonical_payload() -> dict:
    return {
        "company": "Acme Corp",
        "role": "Senior Backend Engineer",
        "seniority": "Senior",
        "required_skills": ["PostgreSQL", "Python", "REST APIs"],
        "preferred_skills": ["Kubernetes", "Terraform"],
        "technologies": ["Docker", "FastAPI", "PostgreSQL", "Python"],
        "domains": ["Backend", "FinTech"],
        "responsibilities": [
            "Design and build scalable backend services",
            "Collaborate with cross-functional teams",
        ],
        "qualifications": ["5+ years of software engineering experience"],
        "nice_to_have": ["Experience with event-driven architectures"],
        "keywords": ["Backend", "FastAPI", "FinTech", "Python", "Senior"],
    }


def _iteration_variants() -> List[str]:
    """
    Five responses of the kind a model returns across five separate calls.

    Each carries the same facts; they differ only in ways that must not
    survive canonicalization.
    """
    base = _canonical_payload()

    # 1. Already canonical.
    first = json.dumps(base)

    # 2. Lists in a different order.
    shuffled = _canonical_payload()
    shuffled["required_skills"] = ["Python", "REST APIs", "PostgreSQL"]
    shuffled["technologies"] = ["Python", "PostgreSQL", "FastAPI", "Docker"]
    shuffled["keywords"] = ["Senior", "Python", "FinTech", "FastAPI", "Backend"]
    shuffled["domains"] = ["FinTech", "Backend"]
    second = json.dumps(shuffled)

    # 3. Duplicates and inconsistent casing.
    duplicated = _canonical_payload()
    duplicated["required_skills"] = [
        "PostgreSQL",
        "postgresql",
        "Python",
        "PYTHON",
        "REST APIs",
    ]
    duplicated["keywords"] = ["Backend", "backend", "FastAPI", "FinTech", "Python", "Senior"]
    duplicated["responsibilities"] = [
        "Design and build scalable backend services",
        "Design and build scalable backend services",
        "Collaborate with cross-functional teams",
    ]
    third = json.dumps(duplicated)

    # 4. Whitespace noise, bullet prefixes and trailing periods.
    noisy = _canonical_payload()
    noisy["role"] = "  Senior   Backend Engineer.  "
    noisy["required_skills"] = [" PostgreSQL ", "Python.", "- REST APIs"]
    noisy["responsibilities"] = [
        "• Design and build scalable backend services.",
        "Collaborate with  cross-functional teams.",
    ]
    noisy["qualifications"] = ["5+ years of software engineering experience."]
    fourth = json.dumps(noisy)

    # 5. Wrapped in a markdown fence, with a skill cross-listed as preferred
    #    and an empty-string company placeholder.
    wrapped = _canonical_payload()
    wrapped["preferred_skills"] = ["Kubernetes", "Python", "Terraform"]
    fifth = "Here is the analysis:\n```json\n" + json.dumps(wrapped) + "\n```\nLet me know."

    return [first, second, third, fourth, fifth]


# ---------------------------------------------------------------------------
# The headline guarantee
# ---------------------------------------------------------------------------


class TestFiveIterations:
    """The same job description analyzed five times yields one result."""

    def test_five_iterations_produce_identical_analyses(self):
        provider = ScriptedProvider(_iteration_variants())
        analyzer = JDAnalyzer(provider=provider)

        results = [analyzer.analyze(JOB_DESCRIPTION) for _ in range(5)]

        assert len(results) == 5
        first = results[0]
        for index, result in enumerate(results[1:], start=2):
            assert result == first, f"iteration {index} differs from iteration 1"

    def test_five_iterations_serialize_identically(self):
        provider = ScriptedProvider(_iteration_variants())
        analyzer = JDAnalyzer(provider=provider)

        dumps = {
            json.dumps(analyzer.analyze(JOB_DESCRIPTION).model_dump(), sort_keys=True)
            for _ in range(5)
        }

        assert len(dumps) == 1

    def test_analysis_matches_the_canonical_payload(self):
        provider = ScriptedProvider(_iteration_variants())
        analyzer = JDAnalyzer(provider=provider)

        result = analyzer.analyze(JOB_DESCRIPTION)

        assert result == JobAnalysis(**_canonical_payload())

    def test_cross_listed_skill_is_removed_from_preferred(self):
        # Variant 5 lists Python as both required and preferred.
        provider = ScriptedProvider([_iteration_variants()[4]])
        analyzer = JDAnalyzer(provider=provider)

        result = analyzer.analyze(JOB_DESCRIPTION)

        assert "Python" in result.required_skills
        assert "Python" not in result.preferred_skills


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


class TestSampling:

    def test_provider_receives_the_deterministic_options(self):
        provider = ScriptedProvider([json.dumps(_canonical_payload())])
        JDAnalyzer(provider=provider).analyze(JOB_DESCRIPTION)

        assert provider.options[0] == dict(DETERMINISTIC_OPTIONS)

    def test_every_call_sends_the_same_options(self):
        provider = ScriptedProvider([json.dumps(_canonical_payload())])
        analyzer = JDAnalyzer(provider=provider)

        for _ in range(5):
            analyzer.analyze(JOB_DESCRIPTION)

        assert all(options == provider.options[0] for options in provider.options)

    def test_greedy_decoding_is_pinned(self):
        assert DETERMINISTIC_OPTIONS["temperature"] == 0.0
        assert DETERMINISTIC_OPTIONS["top_k"] == 1
        assert DETERMINISTIC_OPTIONS["top_p"] == 1.0
        assert DETERMINISTIC_OPTIONS["seed"] == DETERMINISTIC_SEED
        assert DETERMINISTIC_OPTIONS["json_mode"] is True
        assert DETERMINISTIC_OPTIONS["num_ctx"] > 0
        assert DETERMINISTIC_OPTIONS["max_tokens"] > 0

    def test_shared_defaults_cannot_be_mutated(self):
        with pytest.raises(TypeError):
            DETERMINISTIC_OPTIONS["temperature"] = 1.0  # type: ignore[index]

    def test_helper_returns_an_independent_copy(self):
        first = deterministic_options()
        first["temperature"] = 1.0

        assert deterministic_options()["temperature"] == 0.0

    def test_helper_applies_overrides(self):
        assert deterministic_options(max_tokens=64)["max_tokens"] == 64


# ---------------------------------------------------------------------------
# Prompt stability
# ---------------------------------------------------------------------------


class TestPromptStability:

    def test_prompt_is_byte_stable(self):
        prompts = {build_analysis_prompt(JOB_DESCRIPTION) for _ in range(5)}
        assert len(prompts) == 1

    def test_job_description_is_delimited(self):
        prompt = build_analysis_prompt(JOB_DESCRIPTION)
        assert f"<job_description>\n{JOB_DESCRIPTION}\n</job_description>" in prompt

    def test_prompt_forbids_paraphrase(self):
        prompt = build_analysis_prompt(JOB_DESCRIPTION).lower()
        assert "synonym" in prompt
        assert "exactly" in prompt

    def test_analyzer_sends_the_built_prompt(self):
        provider = ScriptedProvider([json.dumps(_canonical_payload())])
        JDAnalyzer(provider=provider).analyze(JOB_DESCRIPTION)

        assert provider.prompts[0] == build_analysis_prompt(JOB_DESCRIPTION)


# ---------------------------------------------------------------------------
# Response wrapper tolerance
# ---------------------------------------------------------------------------


class TestExtraction:

    @pytest.mark.parametrize(
        "wrapper",
        [
            "{body}",
            "```json\n{body}\n```",
            "```\n{body}\n```",
            "Here is the JSON:\n{body}",
            "{body}\n\nLet me know if you need anything else.",
            "  \n{body}\n  ",
        ],
    )
    def test_wrapped_responses_produce_the_same_analysis(self, wrapper):
        body = json.dumps(_canonical_payload())
        analyzer = JDAnalyzer(provider=ScriptedProvider([wrapper.format(body=body)]))

        assert analyzer.analyze(JOB_DESCRIPTION) == JobAnalysis(**_canonical_payload())

    def test_braces_inside_strings_do_not_truncate_the_object(self):
        payload = _canonical_payload()
        payload["responsibilities"] = ["Template rendering with {placeholders}"]
        analyzer = JDAnalyzer(provider=ScriptedProvider([json.dumps(payload)]))

        result = analyzer.analyze(JOB_DESCRIPTION)

        assert result.responsibilities == ["Template rendering with {placeholders}"]

    def test_unbalanced_output_is_still_an_error(self):
        assert extract_json_object("not valid json {{{") == "not valid json {{{"


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


class TestCanonicalization:

    def test_is_idempotent(self):
        once = canonicalize(json.loads(_iteration_variants()[3]))
        twice = canonicalize(once)

        assert once == twice

    def test_does_not_mutate_its_input(self):
        payload = {"required_skills": ["b", "a"]}
        canonicalize(payload)

        assert payload["required_skills"] == ["b", "a"]

    def test_null_list_fields_become_empty_lists(self):
        """
        For a list field, null can only mean "nothing here". Several models
        (gemma4 among them) spell an empty list that way, and rejecting them
        for it would be rejecting a difference that carries no meaning.
        """
        for field in SET_LIKE_FIELDS + PROSE_FIELDS:
            assert canonicalize({field: None})[field] == [], field

    def test_null_lists_do_not_change_the_analysis(self):
        payload = _canonical_payload()
        payload["preferred_skills"] = None
        payload["nice_to_have"] = None

        analyzer = JDAnalyzer(provider=ScriptedProvider([json.dumps(payload)]))
        result = analyzer.analyze(JOB_DESCRIPTION)

        assert result.preferred_skills == []
        assert result.nice_to_have == []

    def test_set_like_fields_are_sorted(self):
        # One field at a time: required_skills and preferred_skills interact,
        # and that interaction is covered separately.
        for field in SET_LIKE_FIELDS:
            result = canonicalize({field: ["b", "C", "a"]})

            assert result[field] == ["a", "b", "C"], field

    def test_prose_fields_keep_job_description_order(self):
        result = canonicalize({field: ["second", "first"] for field in PROSE_FIELDS})

        for field in PROSE_FIELDS:
            assert result[field] == ["second", "first"], field

    def test_prose_fields_are_deduplicated(self):
        result = canonicalize({"responsibilities": ["Ship it", "ship it.", "Test it"]})

        assert result["responsibilities"] == ["Ship it", "Test it"]

    def test_null_equivalents_become_none(self):
        for placeholder in ["", "N/A", "none", "Not mentioned", "-", "unknown"]:
            result = canonicalize({"company": placeholder, "seniority": placeholder})

            assert result["company"] is None, placeholder
            assert result["seniority"] is None, placeholder

    def test_role_is_never_nulled(self):
        # role is required; a placeholder must surface as a validation error
        # rather than be silently converted to None.
        assert canonicalize({"role": "N/A"})["role"] == "N/A"

    def test_abbreviations_keep_their_final_period(self):
        result = canonicalize({"qualifications": ["Ph.D. in Computer Science", "B.S."]})

        assert result["qualifications"] == ["Ph.D. in Computer Science", "B.S."]

    def test_empty_items_are_dropped(self):
        result = canonicalize({"keywords": ["Python", "", "   ", "Go"]})

        assert result["keywords"] == ["Go", "Python"]

    def test_unknown_keys_are_left_for_schema_validation(self):
        result = canonicalize({"unexpected": "value"})

        assert result["unexpected"] == "value"

    def test_wrong_types_are_passed_through(self):
        result = canonicalize({"required_skills": "not a list", "keywords": [1, 2]})

        assert result["required_skills"] == "not a list"
        assert result["keywords"] == [1, 2]
