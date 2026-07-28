"""
Unit tests for ConfigManager.

Covers:
    - save and load round-trip
    - overwrite existing configuration
    - delete configuration
    - exists() before and after save/delete
    - malformed TOML raises ConfigParseError
    - missing file raises ConfigNotFoundError
    - invalid schema raises ConfigValidationError
    - TOML serialization format
"""

import pytest

from src.config.exceptions import (
    ConfigNotFoundError,
    ConfigParseError,
    ConfigValidationError,
)
from src.config.manager import ConfigManager
from src.config.models import ProviderType, ResumeTailorConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path):
    """ConfigManager pointed at a temporary directory."""
    return ConfigManager(config_path=tmp_path / "config.toml")


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


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


class TestExists:
    def test_does_not_exist_initially(self, manager):
        assert manager.exists() is False

    def test_exists_after_save(self, manager, openai_config):
        manager.save(openai_config)
        assert manager.exists() is True

    def test_not_exists_after_delete(self, manager, openai_config):
        manager.save(openai_config)
        manager.delete()
        assert manager.exists() is False


# ---------------------------------------------------------------------------
# save() / load() round-trip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_round_trip_openai(self, manager, openai_config):
        manager.save(openai_config)
        loaded = manager.load()
        assert loaded.provider == ProviderType.OPENAI
        assert loaded.model == "gpt-4o"
        assert loaded.host is None

    def test_round_trip_ollama_with_host(self, manager, ollama_config):
        manager.save(ollama_config)
        loaded = manager.load()
        assert loaded.provider == ProviderType.OLLAMA
        assert loaded.model == "qwen3:32b"
        assert loaded.host == "http://localhost:11434"

    def test_round_trip_anthropic(self, manager):
        config = ResumeTailorConfig(
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4",
        )
        manager.save(config)
        loaded = manager.load()
        assert loaded.provider == ProviderType.ANTHROPIC
        assert loaded.model == "claude-sonnet-4"

    def test_round_trip_gemini(self, manager):
        config = ResumeTailorConfig(
            provider=ProviderType.GEMINI,
            model="gemini-2.5-pro",
        )
        manager.save(config)
        loaded = manager.load()
        assert loaded.provider == ProviderType.GEMINI
        assert loaded.model == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# Overwrite
# ---------------------------------------------------------------------------


class TestOverwrite:
    def test_overwrite_replaces_config(self, manager, openai_config, ollama_config):
        manager.save(openai_config)
        manager.save(ollama_config)
        loaded = manager.load()
        assert loaded.provider == ProviderType.OLLAMA
        assert loaded.model == "qwen3:32b"


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_file(self, manager, openai_config):
        manager.save(openai_config)
        manager.delete()
        assert manager.exists() is False

    def test_delete_is_idempotent(self, manager):
        """Deleting a non-existent config should not raise."""
        manager.delete()
        manager.delete()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoadErrors:
    def test_missing_file_raises_config_not_found(self, manager):
        with pytest.raises(ConfigNotFoundError):
            manager.load()

    def test_malformed_toml_raises_config_parse_error(self, manager, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("provider = [unclosed", encoding="utf-8")
        mgr = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigParseError):
            mgr.load()

    def test_invalid_schema_raises_config_validation_error(self, manager, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            'provider = "unknown_provider"\nmodel = "gpt-4o"\n',
            encoding="utf-8",
        )
        mgr = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigValidationError):
            mgr.load()

    def test_missing_required_field_raises_config_validation_error(
        self, manager, tmp_path
    ):
        config_path = tmp_path / "config.toml"
        # Missing 'model'
        config_path.write_text('provider = "openai"\n', encoding="utf-8")
        mgr = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigValidationError):
            mgr.load()


# ---------------------------------------------------------------------------
# TOML serialization
# ---------------------------------------------------------------------------


class TestTomlSerialization:
    def test_host_not_written_when_none(self, manager, tmp_path, openai_config):
        config_path = tmp_path / "config.toml"
        mgr = ConfigManager(config_path=config_path)
        mgr.save(openai_config)
        content = config_path.read_text(encoding="utf-8")
        assert "host" not in content

    def test_host_written_when_set(self, manager, tmp_path, ollama_config):
        config_path = tmp_path / "config.toml"
        mgr = ConfigManager(config_path=config_path)
        mgr.save(ollama_config)
        content = config_path.read_text(encoding="utf-8")
        assert 'host = "http://localhost:11434"' in content

    def test_provider_value_written_as_string(self, manager, tmp_path, openai_config):
        config_path = tmp_path / "config.toml"
        mgr = ConfigManager(config_path=config_path)
        mgr.save(openai_config)
        content = config_path.read_text(encoding="utf-8")
        assert 'provider = "openai"' in content

    def test_no_secrets_in_file(self, manager, tmp_path, openai_config):
        config_path = tmp_path / "config.toml"
        mgr = ConfigManager(config_path=config_path)
        mgr.save(openai_config)
        content = config_path.read_text(encoding="utf-8")
        assert "api_key" not in content
        assert "secret" not in content
        assert "password" not in content
        assert "token" not in content
