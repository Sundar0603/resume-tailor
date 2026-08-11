"""
Ollama provider implementation for Resume Tailor.

Communicates with a locally running Ollama instance via the official SDK.
No API key is required; authentication is handled by host configuration.
"""

from typing import Any, Dict, List, Optional

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
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send *prompt* to the configured Ollama model and return the response.

        Ollama supports every sampling key in the provider option contract,
        including ``seed`` and ``num_ctx``. Both matter for reproducibility:
        a zero temperature alone still leaves tie-breaking to the sampler,
        and an unpinned context window changes behaviour as the prompt grows.

        Raises
        ------
        ConnectionError
            If the Ollama host cannot be reached.
        ProviderResponseError
            If the response is empty or malformed.
        ProviderError
            For any other Ollama SDK error.
        """
        opts = options or {}
        system_prompt = opts.get("system_prompt")
        temperature = opts.get("temperature", 0.0)
        top_p = opts.get("top_p")
        top_k = opts.get("top_k")
        seed = opts.get("seed")
        num_ctx = opts.get("num_ctx")
        max_tokens = opts.get("max_tokens")
        stop_sequences = opts.get("stop_sequences")
        json_mode = opts.get("json_mode", False)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        ollama_options: dict = {"temperature": temperature}
        if top_p is not None:
            ollama_options["top_p"] = top_p
        if top_k is not None:
            ollama_options["top_k"] = top_k
        if seed is not None:
            ollama_options["seed"] = seed
        if num_ctx is not None:
            ollama_options["num_ctx"] = num_ctx
        if max_tokens is not None:
            ollama_options["num_predict"] = max_tokens
        if stop_sequences:
            ollama_options["stop"] = stop_sequences

        # think=False is required, not an optimisation. Reasoning-capable models
        # (qwen3, qwen3.6, deepseek) otherwise spend the whole num_predict budget
        # on hidden thinking tokens and return an empty message.content, which
        # reaches the caller as an empty-response error indistinguishable from a
        # dead provider. Every caller here wants structured JSON, never
        # chain-of-thought, so reasoning is disabled for all of them.
        chat_kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "options": ollama_options,
            "think": False,
        }
        if json_mode:
            chat_kwargs["format"] = "json"

        try:
            response = self._client.chat(**chat_kwargs)
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
