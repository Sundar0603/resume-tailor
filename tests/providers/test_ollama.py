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
from src.analyzer.sampling import DETERMINISTIC_OPTIONS, deterministic_options
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
            provider.generate("user prompt", options={"system_prompt": "be concise"})

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
            provider.generate("prompt", options={"temperature": 0.7})

            ollama_options = mock_client.chat.call_args.kwargs["options"]
            assert ollama_options["temperature"] == 0.7

    def test_max_tokens_mapped_to_num_predict(self):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("response")

            provider = OllamaProvider(_config())
            provider.generate("prompt", options={"max_tokens": 512})

            ollama_options = mock_client.chat.call_args.kwargs["options"]
            assert ollama_options["num_predict"] == 512

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


# ---------------------------------------------------------------------------
# Deterministic option translation
# ---------------------------------------------------------------------------


class TestOllamaDeterminism:
    """Ollama supports every sampling key in the provider option contract."""

    def _chat_call(self, options):
        with patch("src.providers.ollama.ollama") as mock_ollama:
            mock_client = MagicMock()
            mock_ollama.Client.return_value = mock_client
            mock_client.chat.return_value = _fake_response("{}")

            OllamaProvider(_config()).generate("prompt", options=options)
            return mock_client.chat.call_args.kwargs

    def test_deterministic_options_are_translated(self):
        kwargs = self._chat_call(deterministic_options())
        sent = kwargs["options"]

        assert sent["temperature"] == 0.0
        assert sent["top_k"] == 1
        assert sent["top_p"] == 1.0
        assert sent["seed"] == DETERMINISTIC_OPTIONS["seed"]
        assert sent["num_ctx"] == DETERMINISTIC_OPTIONS["num_ctx"]
        assert sent["num_predict"] == DETERMINISTIC_OPTIONS["max_tokens"]

    def test_json_mode_sets_the_format_flag(self):
        assert self._chat_call(deterministic_options())["format"] == "json"

    def test_reasoning_is_always_disabled(self):
        """
        Reasoning-capable models (qwen3, qwen3.6, deepseek) spend the entire
        num_predict budget on hidden thinking tokens and return an empty
        message.content unless think is False. That surfaces as an
        empty-response error indistinguishable from a dead provider, so this
        flag is a correctness requirement rather than a tuning choice.
        """
        assert self._chat_call(deterministic_options())["think"] is False

    def test_reasoning_stays_disabled_without_options(self):
        assert self._chat_call(None)["think"] is False

    def test_format_omitted_when_json_mode_is_off(self):
        assert "format" not in self._chat_call({"json_mode": False})

    def test_absent_sampling_keys_are_not_invented(self):
        sent = self._chat_call({})["options"]

        for key in ("top_k", "top_p", "seed", "num_ctx", "num_predict"):
            assert key not in sent
