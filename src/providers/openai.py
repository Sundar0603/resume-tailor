"""
OpenAI provider implementation for Resume Tailor.

Communicates with the OpenAI API via the official SDK.
The API key is loaded from the OS credential store via CredentialManager.
"""

from typing import Dict, List, Optional

import openai

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


class OpenAIProvider(LLMProvider):
    """
    LLM provider backed by the OpenAI API.

    Parameters
    ----------
    config : ResumeTailorConfig
        Application configuration. ``config.model`` selects the OpenAI model.
        ``config.host`` optionally overrides the API base URL.
    credentials : CredentialManager
        Used to load the OpenAI API key from the OS credential store.
    """

    def __init__(
        self,
        config: ResumeTailorConfig,
        credentials: CredentialManager,
    ) -> None:
        api_key = credentials.load(ProviderType.OPENAI)
        if not api_key:
            raise AuthenticationError(
                "No OpenAI API key found. "
                "Run 'resume-tailor init' to configure credentials."
            )

        kwargs: dict = {"api_key": api_key}
        if config.host:
            kwargs["base_url"] = config.host

        self._model = config.model
        self._client = openai.OpenAI(**kwargs)

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
        Send *prompt* to the configured OpenAI model and return the response.

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
            For any other OpenAI SDK error.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise AuthenticationError(f"OpenAI authentication failed: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenAI rate limit exceeded: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ConnectionError(f"Could not connect to OpenAI API: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise ConnectionError(f"OpenAI API request timed out: {exc}") from exc
        except openai.APIError as exc:
            raise ProviderError(f"OpenAI API error: {exc}") from exc

        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise ProviderResponseError(
                f"Unexpected OpenAI response structure: {exc}"
            ) from exc

        if not text or not text.strip():
            raise ProviderResponseError("OpenAI returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """Configuration fields required by the OpenAI provider."""
        return ["api_key", "model", "base_url (optional)"]
