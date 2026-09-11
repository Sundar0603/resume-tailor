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
from .canonical import NULL_EQUIVALENTS, canonicalize
from .exceptions import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
    MissingJobRole,
)
from .models import JobAnalysis
from .prompts import build_analysis_prompt
from .provider import LLMProvider
from .role_fallback import resolve_role
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
        MissingJobRole
            If the job description states no job title and no fallback
            title fits it either.
        JobAnalysisValidationError
            If the parsed JSON does not conform to the JobAnalysis schema.
        AnalyzerError
            For any other analyzer-level failure.
        """
        prompt = build_analysis_prompt(job_description)
        raw_response = self._invoke_provider(prompt)
        data = canonicalize(self._parse_json(raw_response))
        self._resolve_role(data, job_description)
        return self._validate(data)

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

    def _resolve_role(self, data: dict, job_description: str) -> None:
        """
        Ensure the payload carries a usable role, inferring one if needed.

        Runs before Pydantic for two reasons. A missing title is an input
        problem, not a schema problem, and reporting it as ``role`` being
        the wrong type tells the user nothing they can act on. And a
        placeholder has to be caught here or not at all: ``min_length=1``
        happily accepts ``"N/A"``, which would then travel the whole
        pipeline as if it were a job title.

        Mutates *data* in place. ``role_inferred`` is always set from this
        side, overwriting anything the model volunteered — provenance is
        the analyzer's to record, not the model's to claim.
        """
        data.pop("role_inferred", None)

        role = data.get("role")
        if isinstance(role, str) and role.strip().casefold() not in NULL_EQUIVALENTS:
            data["role_inferred"] = False
            return

        data["role"] = resolve_role(self._provider, job_description)
        data["role_inferred"] = True

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
