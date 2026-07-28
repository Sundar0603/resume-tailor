"""
Unit tests for configuration models.

Covers:
    - ProviderType enumeration values
    - ResumeTailorConfig valid construction
    - ResumeTailorConfig validation errors (missing fields, empty model, extra fields)
"""

import pytest
from pydantic import ValidationError

from src.config.models import ProviderType, ResumeTailorConfig


# ---------------------------------------------------------------------------
# ProviderType
# ---------------------------------------------------------------------------


class TestProviderType:
    def test_all_providers_defined(self):
        values = {p.value for p in ProviderType}
        assert values == {"ollama", "openai", "anthropic", "gemini", "openrouter"}

    def test_provider_type_is_str(self):
        assert isinstance(ProviderType.OLLAMA.value, str)

    def test_provider_from_string(self):
        assert ProviderType("openai") == ProviderType.OPENAI

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError):
            ProviderType("unknown_provider")


# ---------------------------------------------------------------------------
# ResumeTailorConfig — valid construction
# ---------------------------------------------------------------------------


class TestResumeTailorConfigValid:
    def test_minimal_config(self):
        config = ResumeTailorConfig(provider=ProviderType.OPENAI, model="gpt-4o")
        assert config.provider == ProviderType.OPENAI
        assert config.model == "gpt-4o"
        assert config.host is None

    def test_config_with_host(self):
        config = ResumeTailorConfig(
            provider=ProviderType.OLLAMA,
            model="qwen3:32b",
            host="http://localhost:11434",
        )
        assert config.host == "http://localhost:11434"

    def test_all_providers_accepted(self):
        for provider in ProviderType:
            config = ResumeTailorConfig(provider=provider, model="some-model")
            assert config.provider == provider

    def test_provider_from_string_value(self):
        config = ResumeTailorConfig(provider="anthropic", model="claude-sonnet-4")
        assert config.provider == ProviderType.ANTHROPIC


# ---------------------------------------------------------------------------
# ResumeTailorConfig — validation errors
# ---------------------------------------------------------------------------


class TestResumeTailorConfigInvalid:
    def test_missing_provider_raises(self):
        with pytest.raises(ValidationError):
            ResumeTailorConfig(model="gpt-4o")

    def test_missing_model_raises(self):
        with pytest.raises(ValidationError):
            ResumeTailorConfig(provider=ProviderType.OPENAI)

    def test_empty_model_raises(self):
        with pytest.raises(ValidationError):
            ResumeTailorConfig(provider=ProviderType.OPENAI, model="   ")

    def test_invalid_provider_string_raises(self):
        with pytest.raises(ValidationError):
            ResumeTailorConfig(provider="invalid_provider", model="gpt-4o")

    def test_extra_fields_raises(self):
        with pytest.raises(ValidationError):
            ResumeTailorConfig(
                provider=ProviderType.OPENAI,
                model="gpt-4o",
                api_key="secret",
            )
