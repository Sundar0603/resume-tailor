"""
JDAnalyzer — converts a raw job description into a structured JobAnalysis object.

Responsibilities:
    - Accept raw job description text
    - Construct the analysis prompt
    - Invoke the LLM provider with deterministic sampling parameters
    - Extract and parse the returned JSON
    - Canonicalize the parsed payload
    - Validate with Pydantic
    - Return a JobAnalysis

The analyzer is stateless, side-effect free, and deterministic: the same job
description always yields the same JobAnalysis. Determinism is enforced in
three places — pinned sampling parameters (:mod:`.sampling`), tolerant JSON
extraction (:mod:`._json_extract`), and canonicalization of the parsed
payload (:mod:`.canonical`).

It does not generate resumes, score resumes, or perform ATS optimization.
"""

import json

from pydantic import ValidationError

from ._json_extract import extract_json_object
from .canonical import canonicalize
from .exceptions import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
)
from .models import JobAnalysis
from .prompts import build_analysis_prompt
from .provider import LLMProvider
from .sampling import deterministic_options


class JDAnalyzer:
    """
    Analyzes a raw job description and returns a structured JobAnalysis.

    Usage::

        analyzer = JDAnalyzer(provider=my_provider)
        analysis = analyzer.analyze(job_description)

    The analyzer is stateless. A single instance may be reused across calls.
    """

    def __init__(self, provider: LLMProvider) -> None:
        """
        Initialize the analyzer with an LLM provider.

        Parameters
        ----------
        provider : LLMProvider
            The LLM provider used to generate the analysis.
        """
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, job_description: str) -> JobAnalysis:
        """
        Analyze a raw job description and return a structured JobAnalysis.

        Calling this twice with the same job description returns two equal
        JobAnalysis objects.

        Parameters
        ----------
        job_description : str
            The raw job description text.

        Returns
        -------
        JobAnalysis
            Structured representation of the job description.

        Raises
        ------
        InvalidAnalyzerResponse
            If the provider returns an empty or unexpected response.
        InvalidAnalyzerJSON
            If the provider response cannot be parsed as valid JSON.
        JobAnalysisValidationError
            If the parsed JSON does not conform to the JobAnalysis schema.
        AnalyzerError
            For any other analyzer-level failure.
        """
        prompt = build_analysis_prompt(job_description)
        raw_response = self._invoke_provider(prompt)
        data = self._parse_json(raw_response)
        return self._validate(canonicalize(data))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke_provider(self, prompt: str) -> str:
        """
        Invoke the LLM provider and return the raw response string.

        The provider is always called with the full deterministic option
        set; see :mod:`src.analyzer.sampling` for why temperature alone is
        not enough.
        """
        try:
            response = self._provider.generate(
                prompt, options=deterministic_options()
            )
        except AnalyzerError:
            raise
        except Exception as exc:
            raise AnalyzerError(
                f"LLM provider raised an unexpected error: {exc}"
            ) from exc

        if not response or not response.strip():
            raise InvalidAnalyzerResponse(
                "LLM provider returned an empty response."
            )

        return response.strip()

    def _parse_json(self, raw_response: str) -> dict:
        """
        Parse the raw response string into a dict.

        A code fence or surrounding commentary is stripped first, since a
        model may wrap its answer on one call and not the next. Malformed
        JSON still raises.
        """
        try:
            return json.loads(extract_json_object(raw_response))
        except json.JSONDecodeError as exc:
            raise InvalidAnalyzerJSON(
                f"LLM response is not valid JSON: {exc}"
            ) from exc

    def _validate(self, data: dict) -> JobAnalysis:
        """Validate the parsed dict against the JobAnalysis schema."""
        try:
            return JobAnalysis(**data)
        except ValidationError as exc:
            raise JobAnalysisValidationError(
                f"LLM response does not conform to the JobAnalysis schema: {exc}"
            ) from exc
        except TypeError as exc:
            raise JobAnalysisValidationError(
                f"Unexpected data shape for JobAnalysis: {exc}"
            ) from exc
