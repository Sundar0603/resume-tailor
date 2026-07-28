"""
Ollama provider implementation for Resume Tailor.

Communicates with a locally running Ollama instance via the official SDK.
No API key is required; authentication is handled by host configuration.
"""

from typing import Dict, List, Optional

import ollama

from src.analyzer.provider import LLMProvider
from src.config.models import ResumeTailorConfig

from .base import ConnectionError, ProviderError, ProviderResponseError

_DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    """
    LLM provider backed by a locally running Ollama instance.

    Parameters
    ----------
    config : ResumeTailorConfig
        Application configuration. ``config.model`` selects the Ollama model.
        ``config.host`` overrides the default Ollama host.
    """

    def __init__(self, config: ResumeTailorConfig) -> None:
        host = config.host or _DEFAULT_HOST
        self._model = config.model
        self._client = ollama.Client(host=host)

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
        Send *prompt* to the configured Ollama model and return the response.

        Raises
        ------
        ConnectionError
            If the Ollama host cannot be reached.
        ProviderResponseError
            If the response is empty or malformed.
        ProviderError
            For any other Ollama SDK error.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        options: dict = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if stop_sequences:
            options["stop"] = stop_sequences

        try:
            response = self._client.chat(
                model=self._model,
                messages=messages,
                options=options,
            )
        except ollama.ResponseError as exc:
            raise ProviderError(f"Ollama error: {exc}") from exc
        except Exception as exc:
            # Covers connection refused, host unreachable, etc.
            raise ConnectionError(
                f"Could not connect to Ollama at the configured host: {exc}"
            ) from exc

        try:
            text = response.message.content
        except (AttributeError, KeyError) as exc:
            raise ProviderResponseError(
                f"Unexpected Ollama response structure: {exc}"
            ) from exc

        if not text or not text.strip():
            raise ProviderResponseError("Ollama returned an empty response.")

        return text

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """Configuration fields required by the Ollama provider."""
        return ["host", "model"]
