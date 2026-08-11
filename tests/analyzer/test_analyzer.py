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
from typing import Any, Dict, Optional

import pytest

from src.analyzer import (
    JDAnalyzer,
    JobAnalysis,
    LLMProvider,
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
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
