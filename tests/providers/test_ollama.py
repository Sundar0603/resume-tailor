"""
Unit tests for OllamaProvider.

All tests mock the ollama SDK. No real network requests are made.

Covers:
    - successful generation (with and without system prompt)
    - connection failure
    - invalid model / ResponseError
    - empty response raises ProviderResponseError
    - required_configuration metadata
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.base import ConnectionError, ProviderError, ProviderResponseError
from src.providers.ollama import OllamaProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "qwen3:32b", host: str = "http://localhost:11434") -> ResumeTailorConfig:
    return ResumeTailorConfig(provider=ProviderType.OLLAMA, model=model, host=host)


def _fake_response(content: str) -> SimpleNamespace:
    """Build a minimal object that mimics ollama.ChatResponse."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


class TestOllamaGenerate:
    def test_successful_generation(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("Hello from Ollama")

            provider = OllamaProvider(_config())
            result = provider.generate("Say hello")

            assert result == "Hello from Ollama"

    def test_system_prompt_included_in_messages(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("response")

            provider = OllamaProvider(_config())
            provider.generate("user prompt", system_prompt="be concise")

            call_kwargs = mock_client.chat.call_args
            messages = call_kwargs.kwargs["messages"]
            assert messages[0] == {"role": "system", "content": "be concise"}
            assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_no_system_prompt_sends_only_user_message(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("response")

            provider = OllamaProvider(_config())
            provider.generate("user prompt")

            messages = mock_client.chat.call_args.kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"

    def test_temperature_passed_in_options(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("response")

            provider = OllamaProvider(_config())
            provider.generate("prompt", temperature=0.7)

            options = mock_client.chat.call_args.kwargs["options"]
            assert options["temperature"] == 0.7

    def test_max_tokens_mapped_to_num_predict(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("response")

            provider = OllamaProvider(_config())
            provider.generate("prompt", max_tokens=512)

            options = mock_client.chat.call_args.kwargs["options"]
            assert options["num_predict"] == 512

    def test_default_host_used_when_not_configured(self):
        config = ResumeTailorConfig(provider=ProviderType.OLLAMA, model="llama3")
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("ok")

            OllamaProvider(config)
            mock_ollama.Client.assert_called_once_with(host="http://localhost:11434")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestOllamaErrors:
    def test_response_error_raises_provider_error(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_ollama.ResponseError = Exception
            mock_client.chat.side_effect = Exception("model not found")

            provider = OllamaProvider(_config())
            with pytest.raises((ProviderError, ConnectionError)):
                provider.generate("prompt")

    def test_connection_error_on_network_failure(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
            # Raise a non-ResponseError to trigger the ConnectionError branch
            mock_client.chat.side_effect = OSError("Connection refused")

            provider = OllamaProvider(_config())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_empty_response_raises_provider_response_error(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("")

            provider = OllamaProvider(_config())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")

    def test_whitespace_only_response_raises_provider_response_error(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("   ")

            provider = OllamaProvider(_config())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestOllamaMetadata:
    def test_required_configuration_contains_host_and_model(self):
        fields = OllamaProvider.required_configuration()
        assert "host" in fields
        assert "model" in fields
