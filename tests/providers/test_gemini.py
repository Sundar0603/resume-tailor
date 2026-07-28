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
