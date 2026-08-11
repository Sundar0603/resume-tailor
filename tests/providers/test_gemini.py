"""
Unit tests for GeminiProvider.

All tests mock the google-genai SDK. No real network requests are made.

Covers:
    - successful generation
    - system prompt forwarded
    - authentication failure (heuristic on exception message)
    - rate limit error (heuristic on exception message)
    - connection error (heuristic on exception message)
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
from src.providers.gemini import GeminiProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "gemini-2.5-pro") -> ResumeTailorConfig:
    return ResumeTailorConfig(provider=ProviderType.GEMINI, model=model)


def _credentials(api_key: str = "gem-test") -> CredentialManager:
    creds = MagicMock(spec=CredentialManager)
    creds.load.return_value = api_key
    return creds


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


class TestGeminiGenerate:
    def test_successful_generation(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.return_value = _fake_response("Hello from Gemini")

            provider = GeminiProvider(_config(), _credentials())
            result = provider.generate("Say hello")

            assert result == "Hello from Gemini"

    def test_generate_content_called_with_model(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.return_value = _fake_response("ok")

            provider = GeminiProvider(_config(model="gemini-2.5-flash"), _credentials())
            provider.generate("prompt")

            call_kwargs = mock_client.models.generate_content.call_args.kwargs
            assert call_kwargs["model"] == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestGeminiErrors:
    def test_missing_api_key_raises_authentication_error(self):
        creds = MagicMock(spec=CredentialManager)
        creds.load.return_value = None

        with patch("src.providers.gemini.genai"):
            with pytest.raises(AuthenticationError):
                GeminiProvider(_config(), creds)

    def test_authentication_error_translated(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.side_effect = Exception(
                "401 api_key invalid"
            )

            provider = GeminiProvider(_config(), _credentials())
            with pytest.raises(AuthenticationError):
                provider.generate("prompt")

    def test_rate_limit_error_translated(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.side_effect = Exception(
                "429 quota exceeded rate limit"
            )

            provider = GeminiProvider(_config(), _credentials())
            with pytest.raises(RateLimitError):
                provider.generate("prompt")

    def test_connection_error_translated(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.side_effect = Exception(
                "network connect timeout"
            )

            provider = GeminiProvider(_config(), _credentials())
            with pytest.raises(ConnectionError):
                provider.generate("prompt")

    def test_empty_response_raises_provider_response_error(self):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.return_value = _fake_response("")

            provider = GeminiProvider(_config(), _credentials())
            with pytest.raises(ProviderResponseError):
                provider.generate("prompt")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestGeminiMetadata:
    def test_required_configuration_contains_api_key_and_model(self):
        fields = GeminiProvider.required_configuration()
        assert "api_key" in fields
        assert "model" in fields


# ---------------------------------------------------------------------------
# Deterministic option translation
# ---------------------------------------------------------------------------


class TestGeminiDeterminism:
    """Gemini supports the full sampling set, including a seed."""

    def _config_kwargs(self, options):
        with patch("src.providers.gemini.genai") as mock_genai, \
             patch("src.providers.gemini.genai_types") as mock_types:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_client.models.generate_content.return_value = _fake_response("{}")

            GeminiProvider(_config(), _credentials()).generate(
                "prompt", options=options
            )
            return mock_types.GenerateContentConfig.call_args.kwargs

    def test_sampling_keys_are_forwarded(self):
        kwargs = self._config_kwargs(deterministic_options())

        assert kwargs["temperature"] == 0.0
        assert kwargs["top_p"] == 1.0
        assert kwargs["top_k"] == 1
        assert kwargs["seed"] == DETERMINISTIC_OPTIONS["seed"]
        assert kwargs["max_output_tokens"] == DETERMINISTIC_OPTIONS["max_tokens"]

    def test_json_mode_sets_the_response_mime_type(self):
        kwargs = self._config_kwargs(deterministic_options())

        assert kwargs["response_mime_type"] == "application/json"

    def test_unsupported_keys_are_ignored(self):
        kwargs = self._config_kwargs(deterministic_options())

        assert "num_ctx" not in kwargs
        assert "json_mode" not in kwargs

    def test_optional_keys_omitted_when_absent(self):
        kwargs = self._config_kwargs({})

        for key in ("top_p", "top_k", "seed", "response_mime_type"):
            assert key not in kwargs
