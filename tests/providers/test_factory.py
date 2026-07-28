"""
Unit tests for the updated ProviderFactory.

All provider constructors are mocked so no SDKs are invoked.

Covers:
    - correct provider class returned for each ProviderType
    - unknown provider raises ValueError
    - factory passes credentials to providers that require them
"""

from unittest.mock import MagicMock, patch

import pytest

from src.config.credentials import CredentialManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.factory import ProviderFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(provider: ProviderType, model: str = "some-model") -> ResumeTailorConfig:
    if provider == ProviderType.OLLAMA:
        return ResumeTailorConfig(
            provider=provider, model=model, host="http://localhost:11434"
        )
    return ResumeTailorConfig(provider=provider, model=model)


@pytest.fixture()
def credentials():
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = "fake-api-key"
    return creds


# ---------------------------------------------------------------------------
# Correct provider returned
# ---------------------------------------------------------------------------


class TestFactoryReturnsCorrectProvider:
    def test_ollama_returns_ollama_provider(self, credentials):
        with patch("src.providers.factory.OllamaProvider") as MockOllama:
            ProviderFactory.create(_config(ProviderType.OLLAMA), credentials)
            MockOllama.assert_called_once()

    def test_openai_returns_openai_provider(self, credentials):
        with patch("src.providers.factory.OpenAIProvider") as MockOpenAI:
            ProviderFactory.create(_config(ProviderType.OPENAI), credentials)
            MockOpenAI.assert_called_once()

    def test_anthropic_returns_anthropic_provider(self, credentials):
        with patch("src.providers.factory.AnthropicProvider") as MockAnthropic:
            ProviderFactory.create(_config(ProviderType.ANTHROPIC), credentials)
            MockAnthropic.assert_called_once()

    def test_gemini_returns_gemini_provider(self, credentials):
        with patch("src.providers.factory.GeminiProvider") as MockGemini:
            ProviderFactory.create(_config(ProviderType.GEMINI), credentials)
            MockGemini.assert_called_once()

    def test_openrouter_returns_openrouter_provider(self, credentials):
        with patch("src.providers.factory.OpenRouterProvider") as MockOpenRouter:
            ProviderFactory.create(_config(ProviderType.OPENROUTER), credentials)
            MockOpenRouter.assert_called_once()


# ---------------------------------------------------------------------------
# Credentials forwarded
# ---------------------------------------------------------------------------


class TestFactoryForwardsCredentials:
    def test_openai_receives_credentials(self, credentials):
        with patch("src.providers.factory.OpenAIProvider") as MockOpenAI:
            config = _config(ProviderType.OPENAI)
            ProviderFactory.create(config, credentials)
            _, call_creds = MockOpenAI.call_args.args
            assert call_creds is credentials

    def test_anthropic_receives_credentials(self, credentials):
        with patch("src.providers.factory.AnthropicProvider") as MockAnthropic:
            config = _config(ProviderType.ANTHROPIC)
            ProviderFactory.create(config, credentials)
            _, call_creds = MockAnthropic.call_args.args
            assert call_creds is credentials

    def test_gemini_receives_credentials(self, credentials):
        with patch("src.providers.factory.GeminiProvider") as MockGemini:
            config = _config(ProviderType.GEMINI)
            ProviderFactory.create(config, credentials)
            _, call_creds = MockGemini.call_args.args
            assert call_creds is credentials

    def test_openrouter_receives_credentials(self, credentials):
        with patch("src.providers.factory.OpenRouterProvider") as MockOpenRouter:
            config = _config(ProviderType.OPENROUTER)
            ProviderFactory.create(config, credentials)
            _, call_creds = MockOpenRouter.call_args.args
            assert call_creds is credentials


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


class TestFactoryUnknownProvider:
    def test_unknown_provider_raises_value_error(self, credentials):
        """Force an unknown provider by bypassing the enum."""
        config = MagicMock()
        config.provider = "totally_unknown_provider"

        with pytest.raises(ValueError):
            ProviderFactory.create(config, credentials)
