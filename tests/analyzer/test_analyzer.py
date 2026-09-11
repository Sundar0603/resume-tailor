"""
Unit tests for the Job Description Analyzer.

Covers:
    Valid cases   — complete JD, short JD, JD without company, JD with minimal requirements
    Invalid cases — malformed JSON, missing role, invalid schema, provider failure
    Parsing       — JSON correctly becomes JobAnalysis
    Validation    — invalid responses raise appropriate exceptions

Determinism is covered separately in test_determinism.py.
"""

import json
from typing import Any, Dict, List, Optional

import pytest

from src.analyzer import (
    JDAnalyzer,
    JobAnalysis,
    LLMProvider,
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
    MissingJobRole,
    FALLBACK_ROLES,
)


# ---------------------------------------------------------------------------
# Fake provider helpers
# ---------------------------------------------------------------------------


class FakeProvider(LLMProvider):
    """LLM provider that returns a pre-configured response string."""

    def __init__(self, response: str) -> None:
        self._response = response

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._response


class FailingProvider(LLMProvider):
    """LLM provider that always raises an exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise self._exc


class ScriptedProvider(LLMProvider):
    """
    LLM provider that returns each response in turn.

    The analyzer makes a second call when the job description states no
    job title, so a fallback test needs the analysis response and the
    title response to differ. Records every prompt for assertions.
    """

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.prompts: List[str] = []

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("provider called more times than scripted")
        return self._responses.pop(0)


def _analyzer(response: str) -> JDAnalyzer:
    return JDAnalyzer(provider=FakeProvider(response))


def _json(data: dict) -> str:
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Fixtures — valid payloads
# ---------------------------------------------------------------------------


def _complete_payload() -> dict:
    """
    A complete payload that is already canonical.

    Set-like fields are sorted and free of trailing punctuation, so the
    assertions below can compare against the payload directly. Payloads that
    are *not* canonical are exercised in test_determinism.py.
    """
    return {
        "company": "Acme Corp",
        "role": "Senior Software Engineer",
        "seniority": "Senior",
        "required_skills": ["PostgreSQL", "Python", "REST APIs"],
        "preferred_skills": ["Kubernetes", "Terraform"],
        "technologies": ["Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
        "domains": ["Backend", "FinTech"],
        "responsibilities": [
            "Design and build scalable backend services",
            "Collaborate with cross-functional teams",
        ],
        "qualifications": [
            "5+ years of software engineering experience",
            "Bachelor's degree in Computer Science or equivalent",
        ],
        "nice_to_have": ["Experience with event-driven architectures"],
        "keywords": ["Backend", "FastAPI", "FinTech", "Python", "Senior"],
    }


def _no_company_payload() -> dict:
    payload = _complete_payload()
    payload["company"] = None
    return payload


def _no_seniority_payload() -> dict:
    payload = _complete_payload()
    payload["seniority"] = None
    return payload


def _minimal_payload() -> dict:
    return {
        "company": None,
        "role": "Software Engineer",
        "seniority": None,
        "required_skills": ["Python"],
        "preferred_skills": [],
        "technologies": [],
        "domains": [],
        "responsibilities": [],
        "qualifications": [],
        "nice_to_have": [],
        "keywords": ["Python"],
    }


# ---------------------------------------------------------------------------
# Valid Cases
# ---------------------------------------------------------------------------


class TestValidCases:

    def test_complete_jd(self):
        payload = _complete_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Some full job description text.")

        assert isinstance(result, JobAnalysis)
        assert result.company == "Acme Corp"
        assert result.role == "Senior Software Engineer"
        assert result.seniority == "Senior"
        assert "Python" in result.required_skills
        assert "Kubernetes" in result.preferred_skills
        assert "FastAPI" in result.technologies
        assert "FinTech" in result.domains
        assert len(result.responsibilities) == 2
        assert len(result.qualifications) == 2
        assert len(result.nice_to_have) == 1
        assert "Python" in result.keywords

    def test_short_jd(self):
        payload = _minimal_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Software Engineer role.")

        assert isinstance(result, JobAnalysis)
        assert result.role == "Software Engineer"
        assert result.company is None
        assert result.required_skills == ["Python"]
        assert result.keywords == ["Python"]

    def test_jd_without_company(self):
        payload = _no_company_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("A job description with no company name.")

        assert isinstance(result, JobAnalysis)
        assert result.company is None
        assert result.role == "Senior Software Engineer"

    def test_jd_with_minimal_requirements(self):
        payload = _minimal_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Minimal JD with few requirements.")

        assert isinstance(result, JobAnalysis)
        assert result.preferred_skills == []
        assert result.technologies == []
        assert result.domains == []
        assert result.responsibilities == []
        assert result.qualifications == []
        assert result.nice_to_have == []

    def test_jd_without_seniority(self):
        payload = _no_seniority_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("A job description without explicit seniority.")

        assert isinstance(result, JobAnalysis)
        assert result.seniority is None


# ---------------------------------------------------------------------------
# Invalid Cases
# ---------------------------------------------------------------------------


class TestInvalidCases:

    def test_malformed_json(self):
        analyzer = _analyzer("not valid json {{{")
        with pytest.raises(InvalidAnalyzerJSON):
            analyzer.analyze("Some JD.")

    def test_missing_role(self):
        payload = _complete_payload()
        del payload["role"]
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_unresolvable_role_raises_missing_job_role(self):
        # No title in the job description and no fallback title fits it
        # either: the failure must name the missing title, not the schema.
        payload = _complete_payload()
        payload["role"] = None
        provider = ScriptedProvider(_json(payload), '{"role": "Underwater Basket Weaver"}')
        analyzer = JDAnalyzer(provider=provider)
        with pytest.raises(MissingJobRole):
            analyzer.analyze("Job Requirements\n\n3 to 5 years of experience.")

    def test_missing_job_role_is_a_validation_error(self):
        # Callers catching the general case keep working.
        assert issubclass(MissingJobRole, JobAnalysisValidationError)

    def test_summary_is_rejected_as_an_unknown_field(self):
        # `summary` was removed from JobAnalysis: free-form prose is the
        # least reproducible part of an analysis. A model that still emits
        # one must fail rather than have it silently dropped.
        payload = _complete_payload()
        payload["summary"] = "We are looking for a Senior Software Engineer."
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_empty_role(self):
        payload = _complete_payload()
        payload["role"] = "   "
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_missing_required_skills(self):
        payload = _complete_payload()
        del payload["required_skills"]
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_missing_keywords(self):
        payload = _complete_payload()
        del payload["keywords"]
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_invalid_schema_extra_field(self):
        payload = _complete_payload()
        payload["unknown_field"] = "should not be here"
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_invalid_schema_wrong_type(self):
        payload = _complete_payload()
        payload["required_skills"] = "not a list"
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_provider_raises_analyzer_error(self):
        exc = AnalyzerError("provider down")
        analyzer = JDAnalyzer(provider=FailingProvider(exc))
        with pytest.raises(AnalyzerError):
            analyzer.analyze("Some JD.")

    def test_provider_raises_unexpected_exception(self):
        exc = RuntimeError("network timeout")
        analyzer = JDAnalyzer(provider=FailingProvider(exc))
        with pytest.raises(AnalyzerError):
            analyzer.analyze("Some JD.")

    def test_provider_returns_empty_string(self):
        analyzer = _analyzer("")
        with pytest.raises(InvalidAnalyzerResponse):
            analyzer.analyze("Some JD.")

    def test_provider_returns_whitespace_only(self):
        analyzer = _analyzer("   \n  ")
        with pytest.raises(InvalidAnalyzerResponse):
            analyzer.analyze("Some JD.")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:

    def test_json_becomes_job_analysis(self):
        payload = _complete_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Some JD.")

        assert isinstance(result, JobAnalysis)
        assert result.company == payload["company"]
        assert result.role == payload["role"]
        assert result.seniority == payload["seniority"]
        assert result.required_skills == payload["required_skills"]
        assert result.preferred_skills == payload["preferred_skills"]
        assert result.technologies == payload["technologies"]
        assert result.domains == payload["domains"]
        assert result.responsibilities == payload["responsibilities"]
        assert result.qualifications == payload["qualifications"]
        assert result.nice_to_have == payload["nice_to_have"]
        assert result.keywords == payload["keywords"]

    def test_null_optional_fields_become_none(self):
        payload = _complete_payload()
        payload["company"] = None
        payload["seniority"] = None
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Some JD.")

        assert result.company is None
        assert result.seniority is None

    def test_empty_lists_are_preserved(self):
        payload = _minimal_payload()
        analyzer = _analyzer(_json(payload))
        result = analyzer.analyze("Minimal JD.")

        assert result.preferred_skills == []
        assert result.technologies == []
        assert result.domains == []
        assert result.responsibilities == []
        assert result.qualifications == []
        assert result.nice_to_have == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:

    def test_malformed_json_raises_invalid_analyzer_json(self):
        analyzer = _analyzer("{bad json")
        with pytest.raises(InvalidAnalyzerJSON):
            analyzer.analyze("Some JD.")

    def test_schema_violation_raises_job_analysis_validation_error(self):
        payload = _complete_payload()
        del payload["role"]
        analyzer = _analyzer(_json(payload))
        with pytest.raises(JobAnalysisValidationError):
            analyzer.analyze("Some JD.")

    def test_provider_failure_raises_analyzer_error(self):
        analyzer = JDAnalyzer(provider=FailingProvider(RuntimeError("fail")))
        with pytest.raises(AnalyzerError):
            analyzer.analyze("Some JD.")

    def test_empty_response_raises_invalid_analyzer_response(self):
        analyzer = _analyzer("")
        with pytest.raises(InvalidAnalyzerResponse):
            analyzer.analyze("Some JD.")


# ---------------------------------------------------------------------------
# Fallback job title
# ---------------------------------------------------------------------------


class TestRoleFallback:
    """
    A job description pasted from a careers page routinely loses its
    heading, and with it the job title. Rather than fail, the analyzer
    asks the model to pick a title from a closed list and marks the
    result as inferred.
    """

    @staticmethod
    def _payload_without_role() -> dict:
        payload = _complete_payload()
        payload["role"] = None
        return payload

    def test_null_role_is_resolved_from_the_fallback_list(self):
        provider = ScriptedProvider(
            _json(self._payload_without_role()),
            '{"role": "DevOps Engineer"}',
        )
        result = JDAnalyzer(provider=provider).analyze("Job Requirements\n\nHelm, Jenkins, CI/CD.")
        assert result.role == "DevOps Engineer"
        assert result.role_inferred is True

    def test_absent_role_key_is_resolved_too(self):
        payload = _complete_payload()
        del payload["role"]
        provider = ScriptedProvider(_json(payload), '{"role": "Software Engineer"}')
        result = JDAnalyzer(provider=provider).analyze("Some JD.")
        assert result.role == "Software Engineer"
        assert result.role_inferred is True

    def test_placeholder_role_is_resolved_rather_than_accepted(self):
        # min_length=1 accepts "N/A", which would otherwise travel the
        # whole pipeline as if it were a real job title.
        for placeholder in ("N/A", "none", "Not specified", "   "):
            payload = _complete_payload()
            payload["role"] = placeholder
            provider = ScriptedProvider(_json(payload), '{"role": "Software Developer"}')
            result = JDAnalyzer(provider=provider).analyze("Some JD.")
            assert result.role == "Software Developer"
            assert result.role_inferred is True

    def test_a_stated_role_is_never_inferred(self):
        # The fallback must not fire, and must not cost a second call.
        provider = ScriptedProvider(_json(_complete_payload()))
        result = JDAnalyzer(provider=provider).analyze("Some JD.")
        assert result.role == "Senior Software Engineer"
        assert result.role_inferred is False
        assert len(provider.prompts) == 1

    def test_model_cannot_claim_its_own_role_provenance(self):
        # role_inferred is the analyzer's to record. A model that emits it
        # is overruled either way.
        payload = _complete_payload()
        payload["role_inferred"] = True
        provider = ScriptedProvider(_json(payload))
        assert JDAnalyzer(provider=provider).analyze("Some JD.").role_inferred is False

    def test_fallback_reply_is_matched_leniently(self):
        # A model that decorates the title with a seniority it was told to
        # omit has still chosen a list entry.
        for reply, expected in (
            ('{"role": "software engineer"}', "Software Engineer"),
            ('{"role": "Senior Data Engineer"}', "Data Engineer"),
            ("Platform Engineer", "Platform Engineer"),
            ('```json\n{"role": "QA Engineer"}\n```', "QA Engineer"),
        ):
            provider = ScriptedProvider(_json(self._payload_without_role()), reply)
            result = JDAnalyzer(provider=provider).analyze("Some JD.")
            assert result.role == expected, reply
            assert result.role_inferred is True

    def test_fallback_prompt_lists_every_allowed_title(self):
        provider = ScriptedProvider(
            _json(self._payload_without_role()),
            '{"role": "Software Engineer"}',
        )
        JDAnalyzer(provider=provider).analyze("Some JD.")
        fallback_prompt = provider.prompts[1]
        for role in FALLBACK_ROLES:
            assert role in fallback_prompt

    def test_fallback_is_deterministic(self):
        def run() -> JobAnalysis:
            provider = ScriptedProvider(
                _json(self._payload_without_role()),
                '{"role": "Security Engineer"}',
            )
            return JDAnalyzer(provider=provider).analyze("Some JD.")

        assert run() == run()

    def test_fallback_provider_failure_surfaces_as_missing_role(self):
        class HalfFailingProvider(LLMProvider):
            def __init__(self, first: str) -> None:
                self._first = first
                self._calls = 0

            def generate(self, prompt, options=None):
                self._calls += 1
                if self._calls == 1:
                    return self._first
                raise RuntimeError("provider exploded")

        analyzer = JDAnalyzer(
            provider=HalfFailingProvider(_json(self._payload_without_role()))
        )
        with pytest.raises(MissingJobRole):
            analyzer.analyze("Some JD.")
