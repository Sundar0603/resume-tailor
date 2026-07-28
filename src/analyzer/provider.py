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
from typing import Dict, List, Optional


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
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Send a prompt to the LLM and return the raw text response.

        Parameters
        ----------
        prompt : str
            The user prompt to send to the language model.
        system_prompt : str | None
            An optional system-level instruction prepended to the conversation.
            Providers that do not support system prompts should incorporate it
            into the user prompt or silently ignore it.
        temperature : float
            Sampling temperature. 0.0 produces deterministic output.
            Defaults to 0.0.
        max_tokens : int | None
            Maximum number of tokens to generate. Provider default is used
            when ``None``.
        stop_sequences : list[str] | None
            Optional list of strings that cause generation to stop early.
        extra_headers : dict[str, str] | None
            Optional additional HTTP headers forwarded to the provider API.
            Useful for routing headers (e.g. OpenRouter ``HTTP-Referer``).

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

