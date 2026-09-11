"""
The shared CLI plumbing.

``analyze`` and ``plan`` shipped without tests, so the extraction that now
carries their provider bootstrap and error ladder had no regression net. This
is that net.

The point of interest is the ladder. Both commands depended on an ordering
hazard -- every subclass listed before its base -- which as a chain of
``except`` clauses is invisible and breaks silently when reordered. It is now
an ordered table walked with ``isinstance``, so the ordering is testable, and
these tests are what make it so.
"""

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from src.analyzer.exceptions import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
)
from src.cli import _common
from src.cli._common import (
    DEFAULT_CONTENT_DIRECTORY,
    build_provider,
    fail,
    llm_error_ladder,
    load_configuration,
    read_job_description,
    report_llm_error,
)
from src.planner.exceptions import (
    InvalidPlannerJSON,
    InvalidPlannerResponse,
    PlanConsistencyError,
    PlannerError,
    ResumePlanValidationError,
)
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)

runner = CliRunner(mix_stderr=False)


def echoed(exc: Exception) -> str:
    """Run one exception through the ladder and return what the user sees."""
    app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

    @app.command()
    def command() -> None:
        with llm_error_ladder():
            raise exc

    result = runner.invoke(app, [])
    assert result.exit_code == 1
    return result.stdout


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


class TestTheLadderIsOrdered:
    """
    Every subclass must be matched before its base, or a specific failure gets
    reported as a generic one.
    """

    def test_no_arm_is_shadowed_by_an_earlier_base_class(self):
        # The table is walked with ``isinstance`` and first match wins, so a
        # base class listed before one of its subclasses makes that subclass
        # unreachable and reports a specific failure as a generic one.
        arms = [arm for arm, _, _ in _common._ARMS]
        for index, earlier in enumerate(arms):
            for later in arms[index + 1 :]:
                assert not issubclass(later, earlier), (
                    f"{later.__name__} is a subclass of {earlier.__name__}, "
                    f"which is listed before it, so it can never be reached"
                )

    def test_the_base_classes_are_all_reachable(self):
        arms = {arm for arm, _, _ in _common._ARMS}
        assert {AnalyzerError, PlannerError, ProviderError} <= arms

    def test_what_the_ladder_catches_matches_what_it_reports(self):
        for arm, _, _ in _common._ARMS:
            assert issubclass(arm, _common.LLM_ERRORS)


class TestPlannerArms:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (InvalidPlannerResponse("empty"), "empty or unexpected response"),
            (InvalidPlannerJSON("bad json"), "invalid JSON"),
            (ResumePlanValidationError("schema"), "did not match the expected"),
            (PlanConsistencyError("mismatch"), "inconsistent with the resume"),
            (PlannerError("generic"), "Planner error"),
        ],
    )
    def test_each_arm_has_its_own_message(self, exc, expected):
        assert expected in echoed(exc)

    def test_a_subclass_is_not_reported_as_the_base(self):
        assert "Planner error" not in echoed(InvalidPlannerJSON("bad json"))

    def test_the_underlying_message_survives(self):
        assert "bad json" in echoed(InvalidPlannerJSON("bad json"))


class TestAnalyzerArms:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (InvalidAnalyzerResponse("empty"), "empty or unexpected response"),
            (InvalidAnalyzerJSON("bad json"), "invalid JSON"),
            (JobAnalysisValidationError("schema"), "did not match the expected"),
            (AnalyzerError("generic"), "Analyzer error"),
        ],
    )
    def test_each_arm_has_its_own_message(self, exc, expected):
        assert expected in echoed(exc)

    def test_a_subclass_is_not_reported_as_the_base(self):
        assert "Analyzer error" not in echoed(InvalidAnalyzerJSON("bad json"))


class TestProviderArms:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (AuthenticationError("no key"), "Authentication failed"),
            (ConnectionError("refused"), "Connection failed"),
            (RateLimitError("slow down"), "Rate limit exceeded"),
            (ProviderResponseError("garbled"), "Provider response error"),
            (ProviderError("generic"), "Provider error"),
        ],
    )
    def test_each_arm_has_its_own_message(self, exc, expected):
        assert expected in echoed(exc)

    def test_a_connection_failure_says_what_to_check(self):
        # The one arm that carries remediation, because it is the one a user
        # can usually act on.
        assert "running and reachable" in echoed(ConnectionError("refused"))

    def test_the_other_arms_carry_no_remediation(self):
        assert "running and reachable" not in echoed(RateLimitError("slow down"))


class TestUnrecognisedErrors:
    def test_an_unknown_exception_is_not_reported(self):
        assert report_llm_error(ValueError("who knows")) is False

    def test_an_unknown_exception_propagates(self):
        # A stack trace beats a confident wrong diagnosis.
        app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

        @app.command()
        def command() -> None:
            with llm_error_ladder():
                raise ValueError("who knows")

        result = runner.invoke(app, [])
        assert isinstance(result.exception, ValueError)

    def test_a_clean_body_passes_through(self):
        seen = []
        with llm_error_ladder():
            seen.append("ran")
        assert seen == ["ran"]


# ---------------------------------------------------------------------------
# Configuration and provider
# ---------------------------------------------------------------------------


def run_with(callable_):
    """Invoke a zero-argument callable inside a CLI so ``typer.Exit`` lands."""
    app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

    @app.command()
    def command() -> None:
        callable_()

    return runner.invoke(app, [])


class TestConfiguration:
    def test_an_unconfigured_install_points_at_doctor(self, tmp_path):
        missing = tmp_path / "absent.toml"
        result = run_with(lambda: load_configuration(str(missing)))
        assert result.exit_code == 1
        assert "resume-tailor doctor" in result.stdout

    def test_an_unreadable_config_names_the_problem(self, tmp_path):
        broken = tmp_path / "config.toml"
        broken.write_text("this is not = valid = toml", encoding="utf-8")
        result = run_with(lambda: load_configuration(str(broken)))
        assert result.exit_code == 1
        assert "configuration" in result.stdout.lower()

    def test_a_valid_config_loads(self, config_file):
        assert load_configuration(str(config_file)).model == "qwen3:32b"


class TestProviderConstruction:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (AuthenticationError("no key"), "Authentication failed"),
            (ConnectionError("refused"), "Connection failed"),
            (ProviderError("generic"), "Provider error"),
        ],
    )
    def test_a_failure_to_build_is_reported(self, ollama_config, exc, expected):
        from unittest.mock import patch

        with patch("src.cli._common.ProviderFactory.create", side_effect=exc):
            result = run_with(lambda: build_provider(ollama_config))
        assert result.exit_code == 1
        assert expected in result.stdout


# ---------------------------------------------------------------------------
# Job description input
# ---------------------------------------------------------------------------


class TestJobDescriptionInput:
    def test_a_file_is_read_and_stripped(self, tmp_path):
        path = tmp_path / "jd.md"
        path.write_text("  Backend engineer.  \n", encoding="utf-8")
        assert read_job_description(str(path)) == "Backend engineer."

    def test_a_missing_file_exits(self, tmp_path):
        result = run_with(lambda: read_job_description(str(tmp_path / "absent.md")))
        assert result.exit_code == 1
        assert "job description" in result.stdout.lower()

    def test_an_empty_file_exits(self, tmp_path):
        path = tmp_path / "jd.md"
        path.write_text("\n\n", encoding="utf-8")
        result = run_with(lambda: read_job_description(str(path)))
        assert result.exit_code == 1
        assert "empty" in result.stdout.lower()

    def test_a_paste_is_read_to_eof(self):
        app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
        captured = {}

        @app.command()
        def command() -> None:
            captured["text"] = read_job_description()

        result = runner.invoke(app, [], input="line one\nline two\n")
        assert result.exit_code == 0
        assert captured["text"] == "line one\nline two"

    def test_the_paste_banner_names_the_terminator(self):
        app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

        @app.command()
        def command() -> None:
            read_job_description()

        result = runner.invoke(app, [], input="something\n")
        assert "Ctrl+D" in result.stdout


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestFail:
    def test_it_exits_non_zero_with_the_message(self):
        result = run_with(lambda: fail("something broke"))
        assert result.exit_code == 1
        assert "something broke" in result.stdout

    def test_follow_up_lines_are_printed(self):
        result = run_with(lambda: fail("broke", "", "try this instead"))
        assert "try this instead" in result.stdout


class TestDefaults:
    def test_the_content_directory_is_a_cli_default_not_a_config_key(self):
        # ``ResumeTailorConfig`` is provider-only and forbids extra keys, so a
        # content directory stored there would need two changes to hold a value
        # the command line can default.
        from src.config.models import ResumeTailorConfig

        assert DEFAULT_CONTENT_DIRECTORY == "content"
        assert "content" not in ResumeTailorConfig.model_fields
        assert Path(DEFAULT_CONTENT_DIRECTORY).is_dir()
