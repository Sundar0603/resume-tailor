"""
Gemini provider implementation for Resume Tailor.

Communicates with the Google Gemini API via the official google-genai SDK.
The API key is loaded from the OS credential store via CredentialManager.
"""

from typing import Dict, List, Optional

import google.genai as genai
import google.genai.types as genai_types

from src.analyzer.provider import LLMProvider
from src.config.credentials import CredentialManager
from src.config.models import ProviderType, ResumeTailorConfig

from .base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)


class GeminiProvider(LLMProvider):
    """
    LLM provider backed by the Google Gemini API.

    Parameters
    ----------
    config : ResumeTailorConfig
        Application configuration. ``config.model`` selects the Gemini model.
    credentials : CredentialManager
        Used to load the Gemini API key from the OS credential store.
    """

    def __init__(
        self,
        config: ResumeTailorConfig,
        credentials: CredentialManager,
    ) -> None:
        api_key = credentials.load(ProviderType.GEMINI)
        if not api_key:
            raise AuthenticationError(
                "No Gemini API key found. "
                "Run 'resume-tailor init' to configure credentials."
            )

        self._model = config.model
        self._client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Send *prompt* to the configured Gemini model and return the response.

        Raises
        ------
        AuthenticationError
            If the API key is rejected.
        RateLimitError
            If the API rate-limits the request.
        ConnectionError
            If the API cannot be reached.
        ProviderResponseError
            If the response is empty or malformed.
        ProviderError
            For any other google-genai SDK error.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    stop_sequences=stop_sequences,
                    system_instruction=system_prompt,
                ),
            )
        except Exception as exc:
            exc_type = type(exc).__name__
            exc_str = str(exc).lower()

            if "api_key" in exc_str or "authentication" in exc_str or "permission" in exc_str or "401" in exc_str or "403" in exc_str:
                raise AuthenticationError(
                    f"Gemini authentication failed: {exc}"
                ) from exc
            if "quota" in exc_str or "rate" in exc_str or "429" in exc_str:
                raise RateLimitError(f"Gemini rate limit exceeded: {exc}") from exc
            if "connect" in exc_str or "network" in exc_str or "timeout" in exc_str:
                raise ConnectionError(
                    f"Could not connect to Gemini API: {exc}"
                ) from exc
            raise ProviderError(f"Gemini API error ({exc_type}): {exc}") from exc

        try:
            text = response.text
        except (AttributeError, ValueError) as exc:
            raise ProviderResponseError(
                f"Unexpected Gemini response structure: {exc}"
            ) from exc

        if not text or not text.strip():
            raise ProviderResponseError("Gemini returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """Configuration fields required by the Gemini provider."""
        return ["api_key", "model"]
