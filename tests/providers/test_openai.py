"""
Unit tests for OpenAIProvider.

All tests mock the openai SDK. No real network requests are made.

Covers:
    - successful generation
    - system prompt included
    - authentication failure
    - rate limit error
    - timeout / connection error
    - empty response raises ProviderResponseError
    - missing API key raises AuthenticationError at construction
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
from src.providers.openai import OpenAIProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "gpt-4o") -> ResumeTailorConfig:
    return ResumeTailorConfig(provider=ProviderType.OPENAI, model=model)


def _credentials(api_key: str = "sk-test") -> CredentialManager:
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = api_key
    return creds


def _fake_response(content: str) -> SimpleNamespace:
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    return SimpleNamespace(choices=[choice])


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


class TestOpenAIGenerate:
    def test_successful_generation(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("Hello")

            provider = OpenAIProvider(_config(), _credentials())
            result = provider.generate("Say hello")

            assert result == "Hello"

    def test_system_prompt_included_in_messages(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenAIProvider(_config(), _credentials())
            provider.generate("user prompt", system_prompt="be concise")

            messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert messages[0] == {"role": "system", "content": "be concise"}
            assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_no_system_prompt_sends_only_user_message(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenAIProvider(_config(), _credentials())
            provider.generate("user prompt")

            messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"

    def test_temperature_forwarded(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenAIProvider(_config(), _credentials())
            provider.generate("prompt", temperature=0.5)

            kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert kwargs["temperature"] == 0.5

    def test_max_tokens_forwarded(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("ok")

            provider = OpenAIProvider(_config(), _credentials())
            provider.generate("prompt", max_tokens=256)

            kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert kwargs["max_tokens"] == 256


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestOpenAIErrors:
    def test_missing_api_key_raises_authentication_error(self):
        creds = MagicMock(spec=CredentialManager)
        creds.load.return_value = None

        with patch("src.providers.openai.openai"):
            with pytest.raises(AuthenticationError):
                OpenAIProvider(_config(), creds)

    def test_authentication_error_translated(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_openai.AuthenticationError = type(
                "AuthenticationError", (Exception,), {}
            )
            mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client.chat.completions.create.side_effect = (
                mock_openai.AuthenticationError("bad key")
            )

            provider = OpenAIProvider(_config(), _credentials())
            with pytest.raises(AuthenticationError):
                provider.generate("prompt")

    def test_rate_limit_error_translated(self):
        with patch("src.providers.openai.openai") as mock_openai:
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

            provider = OpenAIProvider(_config(), _credentials())
            with pytest.raises(RateLimitError):
                provider.generate("prompt")

    def test_connection_error_translated(self):
        with patch("src.providers.openai.openai") as mock_openai:
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

            provider = OpenAIProvider(_config(), _credentials())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_timeout_raises_connection_error(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_openai.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client.chat.completions.create.side_effect = (
                mock_openai.APITimeoutError("timed out")
            )

            provider = OpenAIProvider(_config(), _credentials())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_empty_response_raises_provider_response_error(self):
        with patch("src.providers.openai.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _fake_response("")

            provider = OpenAIProvider(_config(), _credentials())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestOpenAIMetadata:
    def test_required_configuration_contains_api_key_and_model(self):
        fields = OpenAIProvider.required_configuration()
        assert "api_key" in fields
        assert "model" in fields
