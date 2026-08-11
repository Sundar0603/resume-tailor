"""
Anthropic provider implementation for Resume Tailor.

Communicates with the Anthropic API via the official SDK.
The API key is loaded from the OS credential store via CredentialManager.
"""

from typing import Any, Dict, List, Optional

import anthropic

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

_DEFAULT_MAX_TOKENS = 8192


class AnthropicProvider(LLMProvider):
    """
    LLM provider backed by the Anthropic API.

    Parameters
    ----------
    config : ResumeTailorConfig
        Application configuration. ``config.model`` selects the Claude model.
    credentials : CredentialManager
        Used to load the Anthropic API key from the OS credential store.
    """

    def __init__(
        self,
        config: ResumeTailorConfig,
        credentials: CredentialManager,
    ) -> None:
        api_key = credentials.load(ProviderType.ANTHROPIC)
        if not api_key:
            raise AuthenticationError(
                "No Anthropic API key found. "
                "Run 'resume-tailor init' to configure credentials."
            )

        self._model = config.model
        self._client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send *prompt* to the configured Claude model and return the response.

        The Anthropic API exposes no seed, and advises against setting
        ``top_p`` and ``temperature`` together, so ``seed``, ``top_p`` and
        ``num_ctx`` are ignored here. Reproducibility rests on
        ``temperature = 0`` with ``top_k = 1``. There is no JSON mode
        either; ``json_mode`` is satisfied by the analyzer prompt and its
        tolerant response parsing.

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
            For any other Anthropic SDK error.
        """
        opts = options or {}
        system_prompt = opts.get("system_prompt")
        temperature = opts.get("temperature", 0.0)
        top_k = opts.get("top_k")
        max_tokens = opts.get("max_tokens")
        stop_sequences = opts.get("stop_sequences")
        extra_headers = opts.get("extra_headers")

        # Anthropic requires max_tokens; fall back to a sensible default.
        effective_max_tokens = max_tokens if max_tokens is not None else _DEFAULT_MAX_TOKENS

        kwargs: dict = {
            "model": self._model,
            "max_tokens": effective_max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if top_k is not None:
            kwargs["top_k"] = top_k
        if system_prompt:
            kwargs["system"] = system_prompt
        if stop_sequences:
            kwargs["stop_sequences"] = stop_sequences
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AuthenticationError(
                f"Anthropic authentication failed: {exc}"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitError(f"Anthropic rate limit exceeded: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ConnectionError(
                f"Could not connect to Anthropic API: {exc}"
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ConnectionError(
                f"Anthropic API request timed out: {exc}"
            ) from exc
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc

        try:
            text = response.content[0].text
        except (AttributeError, IndexError, KeyError) as exc:
            raise ProviderResponseError(
                f"Unexpected Anthropic response structure: {exc}"
            ) from exc

        if not text or not text.strip():
            raise ProviderResponseError("Anthropic returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """Configuration fields required by the Anthropic provider."""
        return ["api_key", "model"]
