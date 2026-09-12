"""
The ``plan`` command.

Like ``analyze``, it shipped without tests and task 019 moved its bootstrap,
its job-description input and its error ladder into ``src/cli/_common.py``.

The ladder's arms are covered once, in ``test_common.py``. What is covered here
is that this command is wired to them, that mode parsing still happens before
anything expensive, and that its pretty-printer still renders a ResumePlan --
which is the largest piece of display code in the CLI and the part a shared
extraction could most easily have broken.
"""

from unittest.mock import patch

import typer
from typer.testing import CliRunner

from src.analyzer.provider import LLMProvider
from src.cli.plan import plan
from src.parser import ResumeParser
from src.planner.exceptions import InvalidPlannerJSON

from tests.pipeline.conftest import PLAN_MARKER, ScriptedProvider

runner = CliRunner()

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
app.command()(plan)

RESUME = "content/backend_resume.md"


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


def jd_file(tmp_path, text="Backend engineer. Java, Spring Boot, MySQL."):
    path = tmp_path / "jd.md"
    path.write_text(text, encoding="utf-8")
    return path


def scripted() -> ScriptedProvider:
    return ScriptedProvider(ResumeParser().parse(RESUME))


class PlanFailsProvider(ScriptedProvider):
    """
    Answers the analysis call, then fails the planning call.

    A provider that raises on *every* call never reaches the planner: the
    analyzer runs first and wraps any foreign exception as an ``AnalyzerError``,
    so the planner arms would go untested.
    """

    def __init__(self, resume, exc: Exception) -> None:
        super().__init__(resume)
        self._exc = exc

    def generate(self, prompt: str, options=None) -> str:
        if PLAN_MARKER in prompt:
            raise self._exc
        return super().generate(prompt, options)


def invoke(config_file, *args, provider=None):
    argv = ["--config", str(config_file)] + list(args)
    with patch(
        "src.cli._common.ProviderFactory.create",
        return_value=provider if provider is not None else scripted(),
    ):
        return runner.invoke(app, argv)


def plan_run(config_file, tmp_path, mode="strict", provider=None):
    return invoke(
        config_file,
        "--resume",
        RESUME,
        "--jd",
        str(jd_file(tmp_path)),
        "--mode",
        mode,
        provider=provider,
    )


class TestASuccessfulPlan:
    def test_it_exits_zero(self, config_file, tmp_path):
        assert plan_run(config_file, tmp_path).exit_code == 0

    def test_every_section_is_printed(self, config_file, tmp_path):
        out = plan_run(config_file, tmp_path).stdout
        for section in ("Resume Plan", "Summary", "Experience", "Projects", "Skills"):
            assert section in out

    def test_the_mode_reaches_the_output(self, config_file, tmp_path):
        assert "Mode: STRICT" in plan_run(config_file, tmp_path, mode="strict").stdout
        assert (
            "Mode: AGGRESSIVE"
            in plan_run(config_file, tmp_path, mode="aggressive").stdout
        )

    def test_entities_are_labelled_by_name_not_by_runtime_id(
        self, config_file, tmp_path
    ):
        # The plan addresses entities by id; the printer resolves them against
        # the resume, which is the whole reason those label helpers exist.
        out = plan_run(config_file, tmp_path).stdout
        assert "Zoho" in out
        assert "exp_001" not in out

    def test_priorities_print_as_names_not_integers(self, config_file, tmp_path):
        # SectionPriority is an IntEnum and serialises as 3, not "MEDIUM".
        out = plan_run(config_file, tmp_path).stdout
        assert "Priority: " in out
        assert "Priority: 3" not in out


class TestFailures:
    def test_an_unknown_mode_is_rejected(self, config_file, tmp_path):
        result = plan_run(config_file, tmp_path, mode="sideways")
        assert result.exit_code == 1
        assert "sideways" in result.stdout

    def test_a_missing_resume_names_the_file(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--resume",
            str(tmp_path / "absent.md"),
            "--jd",
            str(jd_file(tmp_path)),
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_a_missing_job_description_is_reported(self, config_file, tmp_path):
        result = invoke(
            config_file, "--resume", RESUME, "--jd", str(tmp_path / "absent.md")
        )
        assert result.exit_code == 1
        assert "job description" in result.stdout.lower()

    def test_an_empty_job_description_is_reported(self, config_file, tmp_path):
        result = invoke(
            config_file, "--resume", RESUME, "--jd", str(jd_file(tmp_path, "  \n"))
        )
        assert result.exit_code == 1
        assert "empty" in result.stdout.lower()

    def test_an_unconfigured_install_points_at_doctor(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "--config",
                str(tmp_path / "absent.toml"),
                "--resume",
                RESUME,
                "--jd",
                str(jd_file(tmp_path)),
            ],
        )
        assert result.exit_code == 1
        assert "resume-tailor doctor" in result.stdout

    def test_the_planner_arms_are_wired_in(self, config_file, tmp_path):
        result = plan_run(
            config_file,
            tmp_path,
            provider=PlanFailsProvider(
                ResumeParser().parse(RESUME), InvalidPlannerJSON("bad")
            ),
        )
        assert result.exit_code == 1
        assert "invalid JSON" in result.stdout

    def test_the_analyzer_arms_are_wired_in(self, config_file, tmp_path):
        # A provider that fails every call never reaches the planner: the
        # analyzer runs first and wraps anything foreign as an AnalyzerError.
        result = plan_run(
            config_file, tmp_path, provider=FailingProvider(InvalidPlannerJSON("bad"))
        )
        assert result.exit_code == 1
        assert "Analyzer error" in result.stdout

    def test_no_stack_trace_reaches_the_user(self, config_file, tmp_path):
        result = plan_run(
            config_file,
            tmp_path,
            provider=PlanFailsProvider(
                ResumeParser().parse(RESUME), InvalidPlannerJSON("bad")
            ),
        )
        assert "Traceback" not in result.stdout
