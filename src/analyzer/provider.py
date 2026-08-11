"""
Provider abstraction for Resume Tailor.

Defines the interface that all LLM providers must implement.
Both the Job Description Analyzer and the Resume Generator communicate
exclusively through this abstraction, remaining completely provider-agnostic.

Supported providers:
    - Ollama
    - OpenAI
    - Anthropic
    - Gemini
    - OpenRouter
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """
    Abstract base class for all LLM provider implementations.

    Concrete providers must implement :meth:`generate`.
    All other parameters are optional to maximise forward compatibility.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a prompt to the LLM and return the raw text response.

        Parameters
        ----------
        prompt : str
            The user prompt to send to the language model.
        options : dict | None
            Optional dictionary of generation parameters, expressed in a
            provider-agnostic vocabulary. A provider translates the keys its
            API supports and **silently ignores** the rest, so callers may
            always send the full set. Supported keys:

            - ``system_prompt`` (str): System-level instruction prepended to
              the conversation. Providers that do not support system prompts
              should incorporate it into the user prompt or silently ignore it.
            - ``temperature`` (float): Sampling temperature. Defaults to 0.0.
            - ``top_p`` (float): Nucleus sampling cutoff.
            - ``top_k`` (int): Number of candidate tokens considered. ``1``
              means greedy decoding.
            - ``seed`` (int): Random seed. Providers without a seed parameter
              ignore this.
            - ``num_ctx`` (int): Context window size, in tokens. Meaningful
              for local runtimes only; hosted APIs ignore it.
            - ``json_mode`` (bool): Constrain the response to a valid JSON
              object where the provider supports it.
            - ``max_tokens`` (int): Maximum number of tokens to generate.
              Provider default is used when absent.
            - ``stop_sequences`` (list[str]): Strings that cause generation
              to stop early.
            - ``extra_headers`` (dict[str, str]): Additional HTTP headers
              forwarded to the provider API. Useful for routing headers
              (e.g. OpenRouter ``HTTP-Referer``).

            Callers that need reproducible output should send
            :data:`src.analyzer.sampling.DETERMINISTIC_OPTIONS` rather than
            assembling the sampling keys themselves.

        Returns
        -------
        str
            The raw text response from the language model.

        Raises
        ------
        ProviderError
            Base exception for all provider-level failures.
        AuthenticationError
            If the provider rejects the API key.
        ConnectionError
            If the provider cannot be reached.
        RateLimitError
            If the provider rate-limits the request.
        ProviderResponseError
            If the provider returns an unexpected or empty response.
        """

    # ------------------------------------------------------------------
    # Metadata API
    # ------------------------------------------------------------------

    @classmethod
    def required_configuration(cls) -> List[str]:
        """
        Return the list of configuration fields required by this provider.

        The CLI uses this metadata to know what to collect from the user.
        Adding a new provider requires no CLI changes.

        Returns
        -------
        list[str]
            Human-readable names of required configuration fields.
        """
        return []

