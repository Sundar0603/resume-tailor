"""
Unit tests for OpenRouterProvider.

All tests mock the openai SDK. No real network requests are made.

Covers:
    - successful generation
    - system prompt included
    - authentication failure
    - rate limit error
    - connection / timeout error
    - empty response raises ProviderResponseError
    - missing API key raises AuthenticationError at construction
    - default base URL used when host not configured
    - required_configuration metadata
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config.credentials import CredentialManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.openrouter import OpenRouterProvider, _OPENROUTER_BASE_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "anthropic/claude-sonnet-4", host: str = None) -> ResumeTailorConfig:
    return ResumeTailorConfig(
        provider=ProviderType.OPENROUTER,
        model=model,
        host=host,
    )


def _credentials(api_key: str = "or-test") -> CredentialManager:
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = api_key
    return creds


def _fake_response(content: str) -> SimpleNamespace:
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    return SimpleNamespace(choices=[choice])


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


class TestOpenRouterGenerate:
    def test_successful_generation(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("Hello")

            provider = OpenRouterProvider(_config(), _credentials())
            result = provider.generate("Say hello")

            assert result == "Hello"

    def test_system_prompt_included_in_messages(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenRouterProvider(_config(), _credentials())
            provider.generate("user prompt", system_prompt="be concise")

            messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert messages[0] == {"role": "system", "content": "be concise"}
            assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_default_base_url_used_when_host_not_set(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            OpenRouterProvider(_config(), _credentials())

            call_kwargs = mock_openai.OpenAI.call_args.kwargs
            assert call_kwargs["base_url"] == _OPENROUTER_BASE_URL

    def test_custom_host_overrides_base_url(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            OpenRouterProvider(
                _config(host="https://custom.openrouter.example.com/v1"),
                _credentials(),
            )

            call_kwargs = mock_openai.OpenAI.call_args.kwargs
            assert call_kwargs["base_url"] == "https://custom.openrouter.example.com/v1"

    def test_extra_headers_forwarded(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenRouterProvider(_config(), _credentials())
            provider.generate(
                "prompt",
                extra_headers={"HTTP-Referer": "https://myapp.example.com"},
            )

            kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert kwargs["extra_headers"] == {"HTTP-Referer": "https://myapp.example.com"}


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestOpenRouterErrors:
    def test_missing_api_key_raises_authentication_error(self):
        creds = MagicMock(spec=CredentialManager)
        creds.load.return_value = None

        with patch("src.providers.openrouter.openai"):
            with pytest.raises(AuthenticationError):
                OpenRouterProvider(_config(), creds)

    def test_authentication_error_translated(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client.chat.completions.create.side_effect = (
                mock_openai.AuthenticationError("bad key")
            )

            provider = OpenRouterProvider(_config(), _credentials())
            with pytest.raises(AuthenticationError):
                provider.generate("prompt")

    def test_rate_limit_error_translated(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client.chat.completions.create.side_effect = (
                mock_openai.RateLimitError("rate limited")
            )

            provider = OpenRouterProvider(_config(), _credentials())
            with pytest.raises(RateLimitError):
                provider.generate("prompt")

    def test_connection_error_translated(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client.chat.completions.create.side_effect = (
                mock_openai.APIConnectionError("connection refused")
            )

            provider = OpenRouterProvider(_config(), _credentials())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_empty_response_raises_provider_response_error(self):
        with patch("src.providers.openrouter.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("")

            provider = OpenRouterProvider(_config(), _credentials())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestOpenRouterMetadata:
    def test_required_configuration_contains_api_key_and_model(self):
        fields = OpenRouterProvider.required_configuration()
        assert "api_key" in fields
        assert "model" in fields
