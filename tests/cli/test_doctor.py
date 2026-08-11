"""
Unit and integration tests for the ``resume-tailor doctor`` command.

Covers:
    CLI — configuration exists path
    CLI — configuration missing path (first-time setup)
    CLI — interactive configuration flow
    CLI — smoke test success
    CLI — smoke test failure (all error types)
    Provider selection — list is discovered dynamically (no hardcoding)
    Configuration — persisted correctly after setup
    Credentials — stored via CredentialManager after setup
    Integration — CLI -> ProviderFactory -> LLMProvider.generate() invoked correctly
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.analyzer.provider import LLMProvider
from src.cli.doctor import app
from src.config.manager import ConfigManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.factory import ProviderFactory

runner = CliRunner(mix_stderr=False)


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class FakeProvider(LLMProvider):
    """Always returns a fixed response string."""

    def __init__(self, response: str = "Resume Tailor is working.") -> None:
        self._response = response

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._response


class FailingProvider(LLMProvider):
    """Always raises the configured exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise self._exc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ollama_config():
    return ResumeTailorConfig(
        provider=ProviderType.OLLAMA,
        model="qwen3:32b",
        host="http://localhost:11434",
    )


@pytest.fixture()
def openai_config():
    return ResumeTailorConfig(
        provider=ProviderType.OPENAI,
        model="gpt-4o",
    )


@pytest.fixture()
def config_file(tmp_path, ollama_config):
    """A temporary config file pre-populated with Ollama config."""
    manager = ConfigManager(config_path=tmp_path / "config.toml")
    manager.save(ollama_config)
    return tmp_path / "config.toml"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _invoke_doctor(config_path: Path, input_text: str = "") -> object:
    """Invoke the doctor command with a specific config path override."""
    return runner.invoke(app, ["--config", str(config_path)], input=input_text)


# ---------------------------------------------------------------------------
# Provider registry — dynamic discovery
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_available_providers_returns_all_types(self):
        providers = ProviderFactory.available_providers()
        assert set(providers) == set(ProviderType)

    def test_available_providers_contains_no_hardcoded_strings(self):
        """Verify the list comes from ProviderType enum, not literals."""
        providers = ProviderFactory.available_providers()
        for p in providers:
            assert isinstance(p, ProviderType)

    def test_required_fields_ollama(self):
        fields = ProviderFactory.required_fields(ProviderType.OLLAMA)
        assert "host" in fields
        assert "model" in fields

    def test_required_fields_openai(self):
        fields = ProviderFactory.required_fields(ProviderType.OPENAI)
        assert any("api_key" in f for f in fields)
        assert any("model" in f for f in fields)

    def test_required_fields_anthropic(self):
        fields = ProviderFactory.required_fields(ProviderType.ANTHROPIC)
        assert any("api_key" in f for f in fields)
        assert any("model" in f for f in fields)

    def test_required_fields_gemini(self):
        fields = ProviderFactory.required_fields(ProviderType.GEMINI)
        assert any("api_key" in f for f in fields)
        assert any("model" in f for f in fields)

    def test_required_fields_openrouter(self):
        fields = ProviderFactory.required_fields(ProviderType.OPENROUTER)
        assert any("api_key" in f for f in fields)
        assert any("model" in f for f in fields)

    def test_required_fields_unknown_provider_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            ProviderFactory.required_fields(MagicMock())


# ---------------------------------------------------------------------------
# Smoke test success
# ---------------------------------------------------------------------------


class TestSmokeTestSuccess:
    def test_displays_provider_and_model(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Ollama" in result.output
        assert "qwen3:32b" in result.output

    def test_displays_connected_successfully(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Connected successfully" in result.output

    def test_displays_model_response(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Resume Tailor is working." in result.output

    def test_displays_all_checks_passed(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "All checks passed." in result.output

    def test_exit_code_zero(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert result.exit_code == 0

    def test_configuration_loaded_message(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Configuration loaded" in result.output


# ---------------------------------------------------------------------------
# Smoke test failure — all error types
# ---------------------------------------------------------------------------


class TestSmokeTestFailure:
    def _run_with_error(self, config_file, exc):
        with patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FailingProvider(exc),
        ):
            return _invoke_doctor(config_file)

    def test_authentication_error_exit_code(self, config_file):
        result = self._run_with_error(config_file, AuthenticationError("bad key"))
        assert result.exit_code == 1

    def test_authentication_error_message(self, config_file):
        result = self._run_with_error(config_file, AuthenticationError("bad key"))
        assert "Failed to connect" in result.output
        assert "bad key" in result.output

    def test_connection_error_exit_code(self, config_file):
        result = self._run_with_error(config_file, ConnectionError("refused"))
        assert result.exit_code == 1

    def test_connection_error_message(self, config_file):
        result = self._run_with_error(config_file, ConnectionError("refused"))
        assert "Failed to connect" in result.output
        assert "refused" in result.output

    def test_connection_error_ollama_hint(self, config_file):
        """Ollama-specific hint about model installation should appear."""
        result = self._run_with_error(config_file, ConnectionError("refused"))
        assert "model is installed" in result.output

    def test_rate_limit_error_exit_code(self, config_file):
        result = self._run_with_error(config_file, RateLimitError("quota"))
        assert result.exit_code == 1

    def test_rate_limit_error_message(self, config_file):
        result = self._run_with_error(config_file, RateLimitError("quota"))
        assert "Failed to connect" in result.output

    def test_provider_response_error_exit_code(self, config_file):
        result = self._run_with_error(config_file, ProviderResponseError("empty"))
        assert result.exit_code == 1

    def test_provider_error_exit_code(self, config_file):
        result = self._run_with_error(config_file, ProviderError("unknown"))
        assert result.exit_code == 1

    def test_no_stack_trace_in_output(self, config_file):
        """Stack traces must never be shown to the user."""
        result = self._run_with_error(config_file, ConnectionError("refused"))
        assert "Traceback" not in result.output
        assert 'File "' not in result.output


# ---------------------------------------------------------------------------
# Configuration missing — first-time setup
# ---------------------------------------------------------------------------


class TestFirstTimeSetup:
    def test_no_config_shows_setup_prompt(self, tmp_path):
        config_path = tmp_path / "config.toml"
        # Select Ollama (1), host, model
        user_input = "1\nhttp://localhost:11434\nqwen3:32b\n"
        with patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FakeProvider(),
        ):
            result = runner.invoke(
                app,
                ["--config", str(config_path)],
                input=user_input,
            )
        assert "No AI provider is configured" in result.output
        assert "Let's configure Resume Tailor" in result.output

    def test_provider_list_shown_dynamically(self, tmp_path):
        """Every registered provider must appear in the selection menu."""
        config_path = tmp_path / "config.toml"
        user_input = "1\nhttp://localhost:11434\nqwen3:32b\n"
        with patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FakeProvider(),
        ):
            result = runner.invoke(
                app,
                ["--config", str(config_path)],
                input=user_input,
            )
        for provider in ProviderFactory.available_providers():
            assert provider.value.capitalize() in result.output

    def test_config_persisted_after_setup(self, tmp_path):
        config_path = tmp_path / "config.toml"
        user_input = "1\nhttp://localhost:11434\nqwen3:32b\n"
        with patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FakeProvider(),
        ):
            runner.invoke(
                app,
                ["--config", str(config_path)],
                input=user_input,
            )
        assert config_path.exists()
        manager = ConfigManager(config_path=config_path)
        config = manager.load()
        assert config.provider == ProviderType.OLLAMA
        assert config.model == "qwen3:32b"

    def test_credentials_stored_for_api_key_provider(self, tmp_path):
        """API key must be passed to CredentialManager, never written to disk."""
        config_path = tmp_path / "config.toml"
        # Select OpenAI (2), api_key, model, base_url (optional, skip)
        user_input = "2\nsecret-key\ngpt-4o\n\n"
        mock_cred = MagicMock()
        with patch("src.cli.doctor.CredentialManager", return_value=mock_cred), patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FakeProvider(),
        ):
            runner.invoke(
                app,
                ["--config", str(config_path)],
                input=user_input,
            )
        mock_cred.save.assert_called_once_with(ProviderType.OPENAI, "secret-key")

    def test_api_key_not_written_to_config_file(self, tmp_path):
        """The config file must never contain the API key."""
        config_path = tmp_path / "config.toml"
        user_input = "2\nsecret-key\ngpt-4o\n\n"
        with patch(
            "src.cli.doctor.ProviderFactory.create",
            return_value=FakeProvider(),
        ), patch("src.cli.doctor.CredentialManager"):
            runner.invoke(
                app,
                ["--config", str(config_path)],
                input=user_input,
            )
        if config_path.exists():
            content = config_path.read_text()
            assert "secret-key" not in content


# ---------------------------------------------------------------------------
# Integration — CLI -> ProviderFactory -> LLMProvider.generate()
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_generate_called_with_correct_prompts(self, config_file):
        """Verify generate() is invoked with the diagnostic prompts."""
        fake = FakeProvider()
        generate_spy = MagicMock(wraps=fake.generate)
        fake.generate = generate_spy

        with patch("src.cli.doctor.ProviderFactory.create", return_value=fake):
            _invoke_doctor(config_file)

        generate_spy.assert_called_once()
        call_args = generate_spy.call_args
        args = call_args[0] if call_args[0] else ()
        kwargs = call_args[1] if call_args[1] else {}
        options = kwargs.get("options") or (args[1] if len(args) > 1 else {})
        # system_prompt must contain the diagnostic text
        assert "Resume Tailor is working" in options.get("system_prompt", "")
        # temperature must be 0.0
        assert options.get("temperature") == 0.0

    def test_provider_factory_create_called_with_config_and_credentials(
        self, config_file
    ):
        """ProviderFactory.create must receive the loaded config and credentials."""
        with patch(
            "src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()
        ) as mock_create:
            _invoke_doctor(config_file)

        mock_create.assert_called_once()
        args = mock_create.call_args[0]
        assert isinstance(args[0], ResumeTailorConfig)
        assert args[0].provider == ProviderType.OLLAMA

    def test_subsequent_run_skips_setup(self, config_file):
        """When config exists, setup must not be shown."""
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Let's configure" not in result.output
        assert "Select AI Provider" not in result.output

    def test_header_always_displayed(self, config_file):
        with patch("src.cli.doctor.ProviderFactory.create", return_value=FakeProvider()):
            result = _invoke_doctor(config_file)
        assert "Resume Tailor Doctor" in result.output
