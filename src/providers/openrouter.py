"""
OpenRouter provider implementation for Resume Tailor.

OpenRouter exposes an OpenAI-compatible API, so this implementation
reuses the OpenAI SDK pointed at OpenRouter's base URL.
The API key is loaded from the OS credential store via CredentialManager.
"""

from typing import Any, Dict, List, Optional

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

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LLMProvider):
    """
    LLM provider backed by OpenRouter.

    Uses the OpenAI SDK with OpenRouter's base URL and API key.

    Parameters
    ----------
    config : ResumeTailorConfig
        Application configuration. ``config.model`` selects the model
        (e.g. ``anthropic/claude-sonnet-4``).
        ``config.host`` optionally overrides the OpenRouter base URL.
    credentials : CredentialManager
        Used to load the OpenRouter API key from the OS credential store.
    """

    def __init__(
        self,
        config: ResumeTailorConfig,
        credentials: CredentialManager,
    ) -> None:
        api_key = credentials.load(ProviderType.OPENROUTER)
        if not api_key:
            raise AuthenticationError(
                "No OpenRouter API key found. "
                "Run 'resume-tailor init' to configure credentials."
            )

        base_url = config.host or _OPENROUTER_BASE_URL
        self._model = config.model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send *prompt* to the configured model via OpenRouter and return the response.

        OpenRouter accepts the OpenAI parameter set plus ``top_k``, which it
        forwards only to models that support it. ``num_ctx`` is ignored.

        Raises
        ------
        AuthenticationError
            If the API key is rejected.
        RateLimitError
            If OpenRouter rate-limits the request.
        ConnectionError
            If OpenRouter cannot be reached.
        ProviderResponseError
            If the response is empty or malformed.
        ProviderError
            For any other SDK error.
        """
        opts = options or {}
        system_prompt = opts.get("system_prompt")
        temperature = opts.get("temperature", 0.0)
        top_p = opts.get("top_p")
        top_k = opts.get("top_k")
        seed = opts.get("seed")
        max_tokens = opts.get("max_tokens")
        stop_sequences = opts.get("stop_sequences")
        extra_headers = opts.get("extra_headers")
        json_mode = opts.get("json_mode", False)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        if seed is not None:
            kwargs["seed"] = seed
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        if extra_headers:
            kwargs["extra_headers"] = extra_headers
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if top_k is not None:
            # Not part of the OpenAI schema; OpenRouter reads it from the body.
            kwargs["extra_body"] = {"top_k": top_k}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise AuthenticationError(
                f"OpenRouter authentication failed: {exc}"
            ) from exc
        except openai.RateLimitError as exc:
            raise RateLimitError(f"OpenRouter rate limit exceeded: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ConnectionError(
                f"Could not connect to OpenRouter API: {exc}"
            ) from exc
        except openai.APITimeoutError as exc:
            raise ConnectionError(
                f"OpenRouter API request timed out: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise ProviderError(f"OpenRouter API error: {exc}") from exc

        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise ProviderResponseError(
                f"Unexpected OpenRouter response structure: {exc}"
            ) from exc

        if not text or not text.strip():
            raise ProviderResponseError("OpenRouter returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """Configuration fields required by the OpenRouter provider."""
        return ["api_key", "model"]
