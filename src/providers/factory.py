"""
Provider factory for Resume Tailor.

Inspects the configured provider and constructs the appropriate
concrete LLM provider implementation.

The rest of the application must never instantiate providers directly;
all provider construction goes through this factory.
"""

from typing import Dict, List, Type

from src.analyzer.provider import LLMProvider
from src.config.credentials import CredentialManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.anthropic import AnthropicProvider
from src.providers.gemini import GeminiProvider
from src.providers.ollama import OllamaProvider
from src.providers.openai import OpenAIProvider
from src.providers.openrouter import OpenRouterProvider

# Registry maps each ProviderType to the *name* of the module-level class.
# Using names (not direct references) ensures that unittest.mock.patch
# replacements of those names are respected at call time.
_REGISTRY: Dict[ProviderType, str] = {
    ProviderType.OLLAMA: "OllamaProvider",
    ProviderType.OPENAI: "OpenAIProvider",
    ProviderType.ANTHROPIC: "AnthropicProvider",
    ProviderType.GEMINI: "GeminiProvider",
    ProviderType.OPENROUTER: "OpenRouterProvider",
}

import sys as _sys


def _get_provider_class(provider: ProviderType) -> Type[LLMProvider]:
    """Look up the provider class from the current module namespace."""
    class_name = _REGISTRY.get(provider)
    if class_name is None:
        raise ValueError(f"Unknown provider: {provider}")
    module = _sys.modules[__name__]
    return getattr(module, class_name)  # type: ignore[return-value]


class ProviderFactory:
    """
    Factory that constructs a concrete :class:`LLMProvider` from configuration.

    Usage::

        config = manager.load()
        credentials = CredentialManager()
        provider = ProviderFactory.create(config, credentials)

    """

    @staticmethod
    def create(
        config: ResumeTailorConfig,
        credentials: CredentialManager,
    ) -> LLMProvider:
        """
        Construct and return the appropriate LLM provider.

        Parameters
        ----------
        config : ResumeTailorConfig
            The loaded application configuration.
        credentials : CredentialManager
            The credential manager used to retrieve API keys.

        Returns
        -------
        LLMProvider
            A concrete provider instance ready for use.

        Raises
        ------
        ValueError
            If an unknown provider type is encountered.
        """
        provider_class = _get_provider_class(config.provider)

        # Ollama does not require credentials; all others do.
        if config.provider == ProviderType.OLLAMA:
            return provider_class(config)  # type: ignore[call-arg]

        return provider_class(config, credentials)  # type: ignore[call-arg]

    @staticmethod
    def available_providers() -> List[ProviderType]:
        """
        Return the list of all supported provider types in display order.

        The CLI uses this to build the provider selection menu without
        hard-coding any provider names.

        Returns
        -------
        list[ProviderType]
            All registered provider types.
        """
        return list(_REGISTRY.keys())  # ProviderType keys are stable

    @staticmethod
    def required_fields(provider: ProviderType) -> List[str]:
        """
        Return the configuration fields required by *provider*.

        Delegates to the concrete provider class's
        ``required_configuration()`` class method so that the CLI never
        contains provider-specific conditional logic.

        Parameters
        ----------
        provider : ProviderType
            The provider whose required fields are requested.

        Returns
        -------
        list[str]
            Field names/labels as defined by the provider implementation.

        Raises
        ------
        ValueError
            If *provider* is not registered.
        """
        provider_class = _get_provider_class(provider)
        return provider_class.required_configuration()  # type: ignore[attr-defined]
