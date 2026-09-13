"""
The ``tailor`` command's Knowledge Base path.

Task 020 §21: the command must no longer be constrained to one role-specific
resume's contents, and must not make the user decide which projects or
experiences to use. These tests cover the command's own behaviour — which
source it reads, what it says it is doing, and how it fails. The retrieval
itself is covered in ``tests/retrieval/``.
"""

import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from src.analyzer.provider import LLMProvider
from src.cli.tailor import DEFAULT_KNOWLEDGE_BASE, tailor
from src.knowledge import KnowledgeBaseParser
from src.parser import ResumeParser
from src.providers.base import ConnectionError

from tests.pipeline.conftest import ScriptedProvider

runner = CliRunner()

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
app.command()(tailor)

CANONICAL = Path("content/backend_resume.md")
JOB_DESCRIPTION = "Backend engineer. Java, Spring Boot, MySQL, distributed systems."


class FailingProvider(LLMProvider):
    """Raises on every call, so a run stops at the first LLM stage."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(self, prompt: str, **options):
        raise self._exc

    def test_connection(self) -> bool:
        raise self._exc


def jd_file(tmp_path) -> Path:
    path = tmp_path / "jd.md"
    path.write_text(JOB_DESCRIPTION, encoding="utf-8")
    return path


def invoke(config_file, *args, provider=None, input_text=None):
    argv = ["--config", str(config_file)] + list(args)
    with patch(
        "src.cli._common.ProviderFactory.create",
        return_value=provider or FailingProvider(ConnectionError("stopped here")),
    ):
        return runner.invoke(app, argv, input=input_text)


class TestTheKnowledgeBaseIsTheDefault:
    def test_no_flags_reads_the_knowledge_base(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert "Knowledge Base:" in result.stdout
        assert DEFAULT_KNOWLEDGE_BASE in result.stdout

    def test_it_never_asks_which_resume_to_use(self, config_file, tmp_path):
        """
        §21: "Do not force the user to manually decide which projects or
        experiences should be used."
        """
        result = invoke(
            config_file,
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert "Canonical resumes:" not in result.stdout
        assert "Select a resume" not in result.stdout

    def test_it_announces_the_retrieval_stage(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
            provider=ScriptedProvider(KnowledgeBaseParser().parse(DEFAULT_KNOWLEDGE_BASE).as_resume()),
        )
        assert "Retrieving canonical evidence" in result.stdout

    def test_an_explicit_kb_path_is_honoured(self, config_file, tmp_path):
        copied = tmp_path / "my_kb.md"
        copied.write_text(
            Path(DEFAULT_KNOWLEDGE_BASE).read_text(encoding="utf-8"), encoding="utf-8"
        )
        result = invoke(
            config_file,
            "--kb", str(copied),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert str(copied) in result.stdout


class TestTheResumePathIsStillAvailable:
    def test_an_explicit_resume_bypasses_the_knowledge_base(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--resume", str(CANONICAL),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert "Source resume: backend_resume.md" in result.stdout
        assert "Knowledge Base:" not in result.stdout

    def test_it_says_the_run_is_narrower(self, config_file, tmp_path):
        """
        A resume run cannot reach canonical data outside that file. Saying so
        is what stops the flag being read as equivalent to the default.
        """
        result = invoke(
            config_file,
            "--resume", str(CANONICAL),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert "not available to this run" in result.stdout

    def test_a_resume_run_does_not_announce_retrieval(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--resume", str(CANONICAL),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
            provider=ScriptedProvider(ResumeParser().parse(str(CANONICAL))),
        )
        assert "Retrieving canonical evidence" not in result.stdout


class TestFailures:
    def test_a_missing_knowledge_base_is_actionable(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--kb", str(tmp_path / "absent.md"),
            "--jd", str(jd_file(tmp_path)),
        )
        assert result.exit_code == 1
        assert "Knowledge Base not found" in result.stdout
        assert "--resume" in result.stdout

    def test_it_fails_before_announcing_the_load(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--kb", str(tmp_path / "absent.md"),
            "--jd", str(jd_file(tmp_path)),
        )
        assert "Loading canonical data" not in result.stdout

    def test_a_malformed_knowledge_base_is_reported(self, config_file, tmp_path):
        broken = tmp_path / "broken.md"
        broken.write_text("no front matter here\n", encoding="utf-8")
        result = invoke(
            config_file,
            "--kb", str(broken),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert result.exit_code == 1
        assert "Knowledge Base" in result.stdout

    def test_a_knowledge_base_missing_an_id_is_reported(self, config_file, tmp_path):
        text = Path(DEFAULT_KNOWLEDGE_BASE).read_text(encoding="utf-8")
        broken = tmp_path / "no_id.md"
        broken.write_text(text.replace("Id: proj_002\n", "", 1), encoding="utf-8")
        result = invoke(
            config_file,
            "--kb", str(broken),
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert result.exit_code == 1
        assert "Failed to parse the Knowledge Base" in result.stdout


class TestTheKnowledgeBaseIsNeverWritten:
    def test_a_run_leaves_the_file_byte_identical(self, config_file, tmp_path):
        path = Path(DEFAULT_KNOWLEDGE_BASE)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        invoke(
            config_file,
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
            provider=ScriptedProvider(KnowledgeBaseParser().parse(DEFAULT_KNOWLEDGE_BASE).as_resume()),
        )
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    def test_a_failed_run_leaves_it_byte_identical_too(self, config_file, tmp_path):
        path = Path(DEFAULT_KNOWLEDGE_BASE)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        invoke(
            config_file,
            "--jd", str(jd_file(tmp_path)),
            "--output", str(tmp_path / "run"),
        )
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
