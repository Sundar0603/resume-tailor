"""
Unit tests for ProviderFactory (updated for Task 008).

Covers:
    - Factory returns the correct provider type for each ProviderType
    - Unknown provider raises ValueError

All provider constructors are mocked so no SDKs or credentials are needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.config.credentials import CredentialManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.factory import ProviderFactory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def credentials():
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = "fake-api-key"
    return creds


def _config(provider: ProviderType, model: str = "some-model") -> ResumeTailorConfig:
    if provider == ProviderType.OLLAMA:
        return ResumeTailorConfig(
            provider=provider, model=model, host="http://localhost:11434"
        )
    return ResumeTailorConfig(provider=provider, model=model)


# ---------------------------------------------------------------------------
# Factory returns correct provider
# ---------------------------------------------------------------------------


class TestFactoryReturnsCorrectProvider:
    def test_ollama_provider_returned(self, credentials):
        with patch("src.providers.factory.OllamaProvider") as MockOllama:
            ProviderFactory.create(_config(ProviderType.OLLAMA), credentials)
            MockOllama.assert_called_once()

    def test_openai_provider_returned(self, credentials):
        with patch("src.providers.factory.OpenAIProvider") as MockOpenAI:
            ProviderFactory.create(_config(ProviderType.OPENAI), credentials)
            MockOpenAI.assert_called_once()

    def test_anthropic_provider_returned(self, credentials):
        with patch("src.providers.factory.AnthropicProvider") as MockAnthropic:
            ProviderFactory.create(_config(ProviderType.ANTHROPIC), credentials)
            MockAnthropic.assert_called_once()

    def test_gemini_provider_returned(self, credentials):
        with patch("src.providers.factory.GeminiProvider") as MockGemini:
            ProviderFactory.create(_config(ProviderType.GEMINI), credentials)
            MockGemini.assert_called_once()

    def test_openrouter_provider_returned(self, credentials):
        with patch("src.providers.factory.OpenRouterProvider") as MockOpenRouter:
            ProviderFactory.create(_config(ProviderType.OPENROUTER), credentials)
            MockOpenRouter.assert_called_once()


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


class TestUnknownProvider:
    def test_unknown_provider_raises_value_error(self, credentials):
        config = MagicMock()
        config.provider = "totally_unknown_provider"
        with pytest.raises(ValueError):
            ProviderFactory.create(config, credentials)
