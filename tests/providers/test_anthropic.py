"""
Unit tests for AnthropicProvider.

All tests mock the anthropic SDK. No real network requests are made.

Covers:
    - successful generation
    - system prompt forwarded as top-level parameter
    - authentication failure
    - rate limit error
    - connection / timeout error
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
from src.analyzer.sampling import DETERMINISTIC_OPTIONS, deterministic_options
from src.providers.anthropic import AnthropicProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "claude-sonnet-4") -> ResumeTailorConfig:
    return ResumeTailorConfig(provider=ProviderType.ANTHROPIC, model=model)


def _credentials(api_key: str = "ant-test") -> CredentialManager:
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = api_key
    return creds


def _fake_response(text: str) -> SimpleNamespace:
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


class TestAnthropicGenerate:
    def test_successful_generation(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("Hello from Claude")

            provider = AnthropicProvider(_config(), _credentials())
            result = provider.generate("Say hello")

            assert result == "Hello from Claude"

    def test_system_prompt_passed_as_top_level_param(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("ok")

            provider = AnthropicProvider(_config(), _credentials())
            provider.generate("user prompt", options={"system_prompt": "be concise"})

            kwargs = mock_client.messages.create.call_args.kwargs
            assert kwargs["system"] == "be concise"
            assert kwargs["messages"] == [{"role": "user", "content": "user prompt"}]

    def test_no_system_prompt_omits_system_key(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("ok")

            provider = AnthropicProvider(_config(), _credentials())
            provider.generate("user prompt", options={})

            kwargs = mock_client.messages.create.call_args.kwargs
            assert "system" not in kwargs

    def test_default_max_tokens_applied(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("ok")

            provider = AnthropicProvider(_config(), _credentials())
            provider.generate("prompt")

            kwargs = mock_client.messages.create.call_args.kwargs
            assert "max_tokens" in kwargs
            assert kwargs["max_tokens"] > 0

    def test_explicit_max_tokens_forwarded(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("ok")

            provider = AnthropicProvider(_config(), _credentials())
            provider.generate("prompt", options={"max_tokens": 1024})

            kwargs = mock_client.messages.create.call_args.kwargs
            assert kwargs["max_tokens"] == 1024


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestAnthropicErrors:
    def test_missing_api_key_raises_authentication_error(self):
        creds = MagicMock(spec=CredentialManager)
        creds.load.return_value = None

        with patch("src.providers.anthropic.anthropic"):
            with pytest.raises(AuthenticationError):
                AnthropicProvider(_config(), creds)

    def test_authentication_error_translated(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_anthropic.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_anthropic.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_anthropic.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_anthropic.APIError = type("APIError", (Exception,), {})
            mock_client.messages.create.side_effect = (
                mock_anthropic.AuthenticationError("bad key")
            )

            provider = AnthropicProvider(_config(), _credentials())
            with pytest.raises(AuthenticationError):
                provider.generate("prompt")

    def test_rate_limit_error_translated(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_anthropic.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_anthropic.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_anthropic.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_anthropic.APIError = type("APIError", (Exception,), {})
            mock_client.messages.create.side_effect = (
                mock_anthropic.RateLimitError("rate limited")
            )

            provider = AnthropicProvider(_config(), _credentials())
            with pytest.raises(RateLimitError):
                provider.generate("prompt")

    def test_connection_error_translated(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.AuthenticationError = type("AuthenticationError", (Exception,), {})
            mock_anthropic.RateLimitError = type("RateLimitError", (Exception,), {})
            mock_anthropic.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock_anthropic.APITimeoutError = type("APITimeoutError", (Exception,), {})
            mock_anthropic.APIError = type("APIError", (Exception,), {})
            mock_client.messages.create.side_effect = (
                mock_anthropic.APIConnectionError("connection refused")
            )

            provider = AnthropicProvider(_config(), _credentials())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_empty_response_raises_provider_response_error(self):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("")

            provider = AnthropicProvider(_config(), _credentials())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestAnthropicMetadata:
    def test_required_configuration_contains_api_key_and_model(self):
        fields = AnthropicProvider.required_configuration()
        assert "api_key" in fields
        assert "model" in fields


# ---------------------------------------------------------------------------
# Deterministic option translation
# ---------------------------------------------------------------------------


class TestAnthropicDeterminism:
    """
    Anthropic has no seed, and advises against pairing top_p with
    temperature, so determinism rests on temperature 0 with top_k 1.
    """

    def _create_call(self, options):
        with patch("src.providers.anthropic.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = _fake_response("{}")

            AnthropicProvider(_config(), _credentials()).generate(
                "prompt", options=options
            )
            return mock_client.messages.create.call_args.kwargs

    def test_greedy_sampling_is_forwarded(self):
        kwargs = self._create_call(deterministic_options())

        assert kwargs["temperature"] == 0.0
        assert kwargs["top_k"] == 1
        assert kwargs["max_tokens"] == DETERMINISTIC_OPTIONS["max_tokens"]

    def test_unsupported_keys_are_ignored(self):
        kwargs = self._create_call(deterministic_options())

        for key in ("seed", "top_p", "num_ctx", "json_mode", "response_format"):
            assert key not in kwargs

    def test_top_k_omitted_when_absent(self):
        assert "top_k" not in self._create_call({})
