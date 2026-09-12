"""
Shared fixtures for the CLI tests.

Configuration is real, not faked: a ``config.toml`` is written into ``tmp_path``
and passed through the hidden ``--config`` flag, exactly as
``tests/cli/test_doctor.py`` already does. Only the provider is substituted,
and by a hand-written ``LLMProvider`` subclass rather than a mock, matching the
rest of the suite.
"""

from pathlib import Path

import pytest

from src.config.manager import ConfigManager
from src.config.models import ProviderType, ResumeTailorConfig


@pytest.fixture()
def ollama_config():
    return ResumeTailorConfig(
        provider=ProviderType.OLLAMA,
        model="qwen3:32b",
        host="http://localhost:11434",
    )


@pytest.fixture()
def config_file(tmp_path, ollama_config) -> Path:
    """A temporary config file, so no test reads the developer's real one."""
    path = tmp_path / "config.toml"
    ConfigManager(config_path=path).save(ollama_config)
    return path


@pytest.fixture()
def content_dir(tmp_path) -> Path:
    """An empty canonical-resume directory. Tests copy in what they need."""
    directory = tmp_path / "content"
    directory.mkdir()
    return directory


@pytest.fixture(autouse=True)
def delivery_root(tmp_path, monkeypatch) -> Path:
    """
    Point the delivery directory at ``tmp_path`` for every CLI test.

    ``tailor`` files a passing resume outside the repository, under a real
    path on the developer's disk. A test that invokes the command without
    ``--deliver-to`` would otherwise write there -- which is exactly what
    happened, and left eight directories of scripted-provider output sitting
    among real resumes. Autouse because the rule is "no test writes there",
    and a rule that each test has to remember is not that rule.
    """
    root = tmp_path / "delivered"
    monkeypatch.setattr("src.cli.tailor.DEFAULT_DELIVERY_ROOT", str(root))
    return root
