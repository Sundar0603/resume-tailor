"""
The ``analyze`` command.

It shipped without tests, and task 019 moved its provider bootstrap, its job
description input and its error ladder into ``src/cli/_common.py``. A refactor
of untested code is exactly where a regression hides, so this is the net that
should have existed first.

The ladder's arms are covered once, in ``test_common.py``. What is covered here
is that this command is *wired* to them, and that its own pretty-printer still
renders a JobAnalysis.
"""

from unittest.mock import patch

import typer
from typer.testing import CliRunner

from src.analyzer.exceptions import InvalidAnalyzerJSON
from src.analyzer.provider import LLMProvider
from src.cli.analyze import analyze
from src.parser import ResumeParser

from tests.pipeline.conftest import ScriptedProvider

runner = CliRunner()

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
app.command()(analyze)

JOB_DESCRIPTION = "Backend engineer. Java, Spring Boot, MySQL, distributed systems.\n"


class FailingProvider(LLMProvider):
    """Raises whatever it was given, to drive one arm of the ladder."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(self, prompt: str, **options):
        raise self._exc

    def test_connection(self) -> bool:
        raise self._exc

    @classmethod
    def required_configuration(cls):
        return []


def scripted() -> ScriptedProvider:
    return ScriptedProvider(ResumeParser().parse("content/backend_resume.md"))


def invoke(config_file, provider=None, input_text=JOB_DESCRIPTION):
    with patch(
        "src.cli._common.ProviderFactory.create",
        return_value=provider if provider is not None else scripted(),
    ):
        return runner.invoke(app, ["--config", str(config_file)], input=input_text)


class TestASuccessfulAnalysis:
    def test_it_exits_zero(self, config_file):
        assert invoke(config_file).exit_code == 0

    def test_the_analysis_is_printed(self, config_file):
        out = invoke(config_file).stdout
        for section in ("Job Analysis", "Role", "Required Skills"):
            assert section in out

    def test_the_extracted_values_reach_the_output(self, config_file):
        out = invoke(config_file).stdout
        assert "Backend Engineer" in out
        assert "Spring Boot" in out

    def test_the_paste_banner_is_shown(self, config_file):
        # stdin is this command's only input; the terminator must be named.
        assert "Ctrl+D" in invoke(config_file).stdout


class TestFailures:
    def test_an_empty_paste_is_rejected(self, config_file):
        result = invoke(config_file, input_text="")
        assert result.exit_code == 1
        assert "No job description provided" in result.stdout

    def test_an_unconfigured_install_points_at_doctor(self, tmp_path):
        result = runner.invoke(
            app, ["--config", str(tmp_path / "absent.toml")], input=JOB_DESCRIPTION
        )
        assert result.exit_code == 1
        assert "resume-tailor doctor" in result.stdout

    def test_the_error_ladder_is_wired_in(self, config_file):
        result = invoke(config_file, provider=FailingProvider(InvalidAnalyzerJSON("bad")))
        assert result.exit_code == 1
        assert "invalid JSON" in result.stdout

    def test_no_stack_trace_reaches_the_user(self, config_file):
        result = invoke(config_file, provider=FailingProvider(InvalidAnalyzerJSON("bad")))
        assert "Traceback" not in result.stdout
