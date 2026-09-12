"""
The ``tailor`` command, end to end.

``ResumePipeline`` and ``Reporter`` are covered in their own suites, and this
file does not re-test them. What it covers is everything the chain deliberately
does not know about: which resume, which job description, where the artifacts
go, what a failure reads like, and what the exit code is.

Configuration is real. The provider is a hand-written ``LLMProvider`` subclass,
never a mock. ``patch`` appears only to *inject* at a module boundary, which is
the same use ``tests/cli/test_doctor.py`` makes of it.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from src.analyzer.provider import LLMProvider
from src.cli.tailor import (
    delivery_folder_name,
    discover_resumes,
    run_directory,
    tailor,
)
from src.compiler.models import CompilationResult
from src.parser import ResumeParser
from src.planner.models import PlanningMode
from src.providers.base import ConnectionError
from src.revision.exceptions import OnePageInfeasibleError

from tests.pipeline.conftest import ScriptedProvider
from tests.planner.conftest import make_job_analysis
from tests.report.conftest import make_pipeline_result
from tests.revision.conftest import failing_result

runner = CliRunner()

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
app.command()(tailor)

CANONICAL = Path("content/backend_resume.md")
JOB_DESCRIPTION = "Backend engineer. Java, Spring Boot, MySQL, distributed systems."

needs_tex = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FailingProvider(LLMProvider):
    """Raises on every call, so a run stops at the first LLM stage."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(self, prompt: str, **options):
        raise self._exc

    def test_connection(self) -> bool:
        raise self._exc

    @classmethod
    def required_configuration(cls):
        return []


def place(content_dir: Path, *names: str) -> None:
    """Copy the canonical backend resume in under each of ``names``."""
    for name in names:
        shutil.copy(CANONICAL, content_dir / name)


def scripted_provider() -> ScriptedProvider:
    return ScriptedProvider(ResumeParser().parse(str(CANONICAL)), rewrite=True)


def jd_file(tmp_path: Path, text: str = JOB_DESCRIPTION) -> Path:
    path = tmp_path / "jd.md"
    path.write_text(text, encoding="utf-8")
    return path


def invoke(config_file, *args, provider=None, input_text=None):
    """Run the command with a provider substituted at the CLI boundary."""
    argv = ["--config", str(config_file)] + list(args)
    with patch(
        "src.cli._common.ProviderFactory.create",
        return_value=provider if provider is not None else scripted_provider(),
    ):
        return runner.invoke(app, argv, input=input_text)


class StubPipeline:
    """
    Stands in for ``ResumePipeline`` at the CLI boundary.

    Subclasses decide what one run does. Nothing here reimplements the chain --
    these tests are about what the command does with a result, not how the
    result was reached.
    """

    result = None
    error = None

    def __init__(self, provider, **kwargs):
        pass

    def run(self, **kwargs):
        Path(kwargs["output_directory"]).mkdir(parents=True, exist_ok=True)
        if type(self).error is not None:
            raise type(self).error
        for stage in ("analyze", "plan", "generate", "render", "compile", "quality"):
            kwargs["on_stage"](stage)
        return type(self).result


def stub_pipeline(result=None, error=None):
    return type("_Stub", (StubPipeline,), {"result": result, "error": error})


def compiled_result(pdf: Path, **overrides):
    """A passing run whose final PDF is a file that actually exists."""
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    return make_pipeline_result(
        compilation=CompilationResult(
            pdf_path=str(pdf),
            log_path=str(pdf.with_suffix(".log")),
            tex_path=str(pdf.with_suffix(".tex")),
            engine="pdflatex",
            exit_code=0,
            duration_seconds=0.1,
        ),
        **overrides,
    )


# ---------------------------------------------------------------------------
# Canonical resume discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    """
    The project supports an arbitrary number of canonical resumes, so nothing
    may hardcode how many there are or what they are called.
    """

    def test_it_finds_every_markdown_file(self, content_dir):
        place(content_dir, "a_resume.md", "b_resume.md", "c_resume.md")
        found = discover_resumes(str(content_dir))
        assert [p.name for p in found] == [
            "a_resume.md",
            "b_resume.md",
            "c_resume.md",
        ]

    def test_it_ignores_everything_that_is_not_markdown(self, content_dir):
        place(content_dir, "a_resume.md")
        (content_dir / "notes.txt").write_text("x", encoding="utf-8")
        (content_dir / "old.pdf").write_bytes(b"%PDF-1.4\n")
        assert [p.name for p in discover_resumes(str(content_dir))] == ["a_resume.md"]

    def test_a_missing_directory_is_not_an_exception(self, tmp_path):
        assert discover_resumes(str(tmp_path / "nope")) == []

    def test_the_order_is_stable(self, content_dir):
        place(content_dir, "c_resume.md", "a_resume.md", "b_resume.md")
        first = discover_resumes(str(content_dir))
        second = discover_resumes(str(content_dir))
        assert first == second


class TestSelection:
    def test_no_canonical_resume_is_an_actionable_error(self, config_file, content_dir):
        result = invoke(config_file, "--content-dir", str(content_dir))
        assert result.exit_code == 1
        assert "No canonical resume found" in result.stdout
        assert "--resume" in result.stdout

    def test_a_single_resume_is_selected_without_a_prompt(
        self, config_file, content_dir, tmp_path
    ):
        place(content_dir, "only_resume.md")
        result = invoke(
            config_file,
            "--content-dir",
            str(content_dir),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
            provider=FailingProvider(ConnectionError("stopped here")),
        )
        assert "Source resume: only_resume.md" in result.stdout
        assert "Canonical resumes:" not in result.stdout

    def test_several_resumes_are_offered_and_the_choice_is_honoured(
        self, config_file, content_dir, tmp_path
    ):
        place(content_dir, "alpha_resume.md", "beta_resume.md", "gamma_resume.md")
        result = invoke(
            config_file,
            "--content-dir",
            str(content_dir),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
            provider=FailingProvider(ConnectionError("stopped here")),
            input_text="2\n",
        )
        assert "Canonical resumes:" in result.stdout
        assert "1. alpha_resume" in result.stdout
        assert "Source resume: beta_resume.md" in result.stdout

    def test_an_out_of_range_choice_fails_clearly(
        self, config_file, content_dir, tmp_path
    ):
        place(content_dir, "alpha_resume.md", "beta_resume.md")
        result = invoke(
            config_file,
            "--content-dir",
            str(content_dir),
            input_text="9\n",
        )
        assert result.exit_code == 1
        assert "not one of the 2 resumes" in result.stdout

    def test_an_explicit_resume_skips_discovery(
        self, config_file, content_dir, tmp_path
    ):
        # The content directory is empty, which would otherwise be a hard error.
        result = invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--content-dir",
            str(content_dir),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
            provider=FailingProvider(ConnectionError("stopped here")),
        )
        assert "No canonical resume found" not in result.stdout
        assert "Source resume: backend_resume.md" in result.stdout

    def test_a_missing_resume_file_is_caught_before_it_is_announced(
        self, config_file, tmp_path
    ):
        # Announcing "Source resume: absent.md" and only then failing reads as
        # though the load succeeded.
        result = invoke(
            config_file,
            "--resume",
            str(tmp_path / "absent.md"),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout
        assert "Source resume: absent.md" not in result.stdout
        assert "Loading source resume" not in result.stdout


# ---------------------------------------------------------------------------
# Job description input
# ---------------------------------------------------------------------------


class TestJobDescriptionInput:
    def test_it_reads_a_file(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
            provider=FailingProvider(ConnectionError("stopped here")),
        )
        assert "Paste the job description" not in result.stdout

    def test_a_missing_file_names_the_problem(self, config_file, tmp_path):
        result = invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--jd",
            str(tmp_path / "absent.md"),
        )
        assert result.exit_code == 1
        assert "job description" in result.stdout.lower()

    def test_an_empty_file_is_rejected(self, config_file, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("   \n", encoding="utf-8")
        result = invoke(
            config_file, "--resume", str(CANONICAL), "--jd", str(empty)
        )
        assert result.exit_code == 1
        assert "empty" in result.stdout.lower()

    def test_a_large_multiline_paste_is_read_whole(self, config_file, tmp_path):
        # There is no artificial size limit: a job description is a few
        # kilobytes of text and is read to EOF.
        pasted = "\n".join(f"Requirement {n}: Java, Spring Boot." for n in range(400))
        captured = {}

        class _Capturing(StubPipeline):
            result = make_pipeline_result()

            def run(self, **kwargs):
                captured["jd"] = kwargs["job_description"]
                return super().run(**kwargs)

        with patch("src.cli.tailor.ResumePipeline", _Capturing):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--output",
                str(tmp_path / "run"),
                input_text=pasted,
            )
        assert result.exit_code == 0
        assert len(captured["jd"]) > 5000
        assert captured["jd"].count("\n") == 399

    def test_an_empty_paste_is_rejected(self, config_file, tmp_path):
        result = invoke(
            config_file, "--resume", str(CANONICAL), input_text=""
        )
        assert result.exit_code == 1
        assert "No job description provided" in result.stdout


# ---------------------------------------------------------------------------
# Run directories
# ---------------------------------------------------------------------------


class TestRunDirectories:
    def test_the_name_carries_the_resume_and_the_mode(self):
        directory = run_directory(Path("content/backend_resume.md"), PlanningMode.STRICT)
        assert directory.name.startswith("backend_strict_")

    def test_two_runs_do_not_collide(self, tmp_path):
        # A name carrying only resume and mode overwrites on re-run, leaving
        # the previous run's report beside the new run's PDF.
        first = run_directory(Path("x_resume.md"), PlanningMode.AGGRESSIVE)
        assert "aggressive" in first.name

    def test_a_second_run_leaves_the_first_intact(
        self, config_file, tmp_path, delivery_root
    ):
        # Both runs are delivered, and the second must not land on the first.
        for name in ("run_one", "run_two"):
            stub = stub_pipeline(
                result=compiled_result(tmp_path / name / "resume.pdf")
            )
            with patch("src.cli.tailor.ResumePipeline", stub):
                outcome = invoke(
                    config_file,
                    "--resume",
                    str(CANONICAL),
                    "--jd",
                    str(jd_file(tmp_path)),
                    "--output",
                    str(tmp_path / name),
                )
            assert outcome.exit_code == 0

        for folder in ("Globex-BackendEngineer", "Globex-BackendEngineer-2"):
            artifacts = delivery_root / folder / "artifacts"
            assert (artifacts / "report.md").is_file()
            assert (artifacts / "report.json").is_file()


# ---------------------------------------------------------------------------
# Reporting and exit codes
# ---------------------------------------------------------------------------


class TestSuccess:
    def test_the_three_reports_are_written(
        self, config_file, tmp_path, delivery_root
    ):
        stub = stub_pipeline(result=compiled_result(tmp_path / "run" / "resume.pdf"))
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert result.exit_code == 0
        assert "Done." in result.stdout
        artifacts = delivery_root / "Globex-BackendEngineer" / "artifacts"
        for name in ("report.md", "changes.md", "report.json"):
            assert (artifacts / name).is_file()
            assert name in result.stdout

    def test_every_stage_is_ticked(self, config_file, tmp_path):
        stub = stub_pipeline(result=make_pipeline_result())
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        for label in (
            "Loading source resume",
            "Analyzing job description",
            "Planning changes",
            "Generating resume",
            "Rendering LaTeX",
            "Compiling PDF",
            "Checking layout",
            "Generating report",
        ):
            assert label in result.stdout

    def test_no_confirmation_is_ever_requested(self, config_file, tmp_path):
        # Once the run begins it is autonomous.
        stub = stub_pipeline(result=make_pipeline_result())
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        lowered = result.stdout.lower()
        for prompt in ("do you want to continue", "review this", "accept", "[y/n]"):
            assert prompt not in lowered


class TestFailure:
    def test_a_failing_quality_gate_is_not_reported_as_success(
        self, config_file, tmp_path
    ):
        stub = stub_pipeline(
            result=make_pipeline_result(
                quality=failing_result(), initial_quality=failing_result()
            )
        )
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert result.exit_code == 1
        assert "Done." not in result.stdout
        assert "did not pass the quality gate" in result.stdout

    def test_a_failing_run_still_writes_its_report(self, config_file, tmp_path):
        # A failing run is exactly when the report is most worth having.
        stub = stub_pipeline(
            result=make_pipeline_result(
                quality=failing_result(), initial_quality=failing_result()
            )
        )
        with patch("src.cli.tailor.ResumePipeline", stub):
            invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert (tmp_path / "run" / "report.md").is_file()

    def test_the_blocking_findings_are_named(self, config_file, tmp_path):
        stub = stub_pipeline(
            result=make_pipeline_result(
                quality=failing_result(), initial_quality=failing_result()
            )
        )
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert "INVALID_PAGE_COUNT" in result.stdout

    def test_an_infeasible_one_page_target_reports_its_evidence(
        self, config_file, tmp_path
    ):
        # No PipelineResult exists, so no report can describe this run. The
        # evidence is the trail and the last PDF, and the command must say so.
        error = OnePageInfeasibleError(
            "floors reached with 6 lines still overflowing",
            spill=6,
            steps_taken=11,
            pdf_path=str(tmp_path / "run" / "work" / "resume.pdf"),
            trail_path=str(tmp_path / "run" / "revision_trail.json"),
        )
        with patch("src.cli.tailor.ResumePipeline", stub_pipeline(error=error)):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert result.exit_code == 1
        assert "Could not fit the resume onto one page" in result.stdout
        assert "6" in result.stdout
        assert "revision_trail.json" in result.stdout
        assert "No report was written" in result.stdout
        assert not (tmp_path / "run" / "report.md").exists()

    def test_a_provider_failure_mid_run_names_the_stage(self, config_file, tmp_path):
        # A transport failure raised *inside* a stage arrives wrapped: each AI
        # package re-raises its own errors untouched and wraps everything else,
        # so this surfaces as an analyzer failure. The underlying message must
        # still survive, or the run is undebuggable.
        result = invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
            provider=FailingProvider(ConnectionError("host unreachable")),
        )
        assert result.exit_code == 1
        assert "Analyzer error" in result.stdout
        assert "host unreachable" in result.stdout

    def test_a_provider_that_cannot_be_built_names_the_connection(
        self, config_file, tmp_path
    ):
        # Raised by the factory rather than by a stage, so it reaches the
        # provider ladder unwrapped and gets the remediation line.
        argv = [
            "--config",
            str(config_file),
            "--resume",
            str(CANONICAL),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
        ]
        with patch(
            "src.cli._common.ProviderFactory.create",
            side_effect=ConnectionError("host unreachable"),
        ):
            result = runner.invoke(app, argv)
        assert result.exit_code == 1
        assert "Connection failed" in result.stdout

    def test_an_unknown_mode_is_rejected_before_anything_runs(
        self, config_file, tmp_path
    ):
        result = invoke(config_file, "--mode", "sideways")
        assert result.exit_code == 1
        assert "sideways" in result.stdout

    def test_no_stack_trace_reaches_the_user(self, config_file, tmp_path):
        for args, provider in (
            (["--mode", "sideways"], None),
            (["--resume", str(tmp_path / "absent.md")], None),
            (
                [
                    "--resume",
                    str(CANONICAL),
                    "--jd",
                    str(jd_file(tmp_path)),
                    "--output",
                    str(tmp_path / "run"),
                ],
                FailingProvider(ConnectionError("nope")),
            ),
        ):
            result = invoke(config_file, *args, provider=provider)
            assert "Traceback" not in result.stdout
            assert result.exit_code == 1


# ---------------------------------------------------------------------------
# The real chain
# ---------------------------------------------------------------------------


def _only_delivery(root: Path) -> Path:
    """The single directory a run was delivered into."""
    delivered = sorted(path for path in root.iterdir() if path.is_dir())
    assert len(delivered) == 1, f"expected one delivery, found {delivered}"
    return delivered[0]


class TestTheRealChain:
    """
    One run through the actual pipeline, with only the LLM scripted.

    The stubbed tests above prove the command's own behaviour. This proves the
    command is wired to the real thing -- the seam that survives every unit
    test and then fails once.
    """

    @needs_tex
    def test_a_real_run_produces_a_pdf_and_three_reports(
        self, config_file, tmp_path, delivery_root
    ):
        destination = tmp_path / "run"
        result = invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--jd",
            str(jd_file(tmp_path)),
            "--mode",
            "strict",
            "--output",
            str(destination),
        )
        assert result.exit_code == 0, result.stdout
        assert "Quality gate passed" in result.stdout

        # A passing run is delivered, so the working directory is consumed
        # and the artifacts are found under the company and role.
        assert not destination.exists()
        delivered = _only_delivery(delivery_root)
        assert (delivered / "Resume.pdf").is_file()

        artifacts = delivered / "artifacts"
        assert list(artifacts.glob("**/*.pdf")), "no PDF was produced"

        for name in ("report.md", "changes.md", "report.json"):
            assert (artifacts / name).is_file()

        payload = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
        assert payload["final_verdict"]["passed"] is True

    @needs_tex
    def test_the_generated_markdown_lands_beside_the_reports(
        self, config_file, tmp_path, delivery_root
    ):
        invoke(
            config_file,
            "--resume",
            str(CANONICAL),
            "--jd",
            str(jd_file(tmp_path)),
            "--output",
            str(tmp_path / "run"),
        )
        artifacts = _only_delivery(delivery_root) / "artifacts"
        assert (artifacts / "generated.md").is_file()


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class TestDeliveryNames:
    """
    The directory name is read by a human looking for the resume they sent,
    so it carries the company and the role and nothing about the machinery.
    """

    def test_the_company_and_the_role_are_joined(self):
        analysis = make_job_analysis().model_copy(
            update={"company": "Amazon", "role": "Full Stack Developer"}
        )
        assert delivery_folder_name(analysis) == "Amazon-FullStackDeveloper"

    def test_punctuation_and_spacing_do_not_reach_the_path(self):
        analysis = make_job_analysis().model_copy(
            update={"company": "Acme, Inc.", "role": "Sr. Engineer (Backend)"}
        )
        assert delivery_folder_name(analysis) == "AcmeInc-SrEngineerBackend"

    def test_casing_inside_a_word_survives(self):
        # Upper-casing the whole word would file iOS work under "IOS".
        analysis = make_job_analysis().model_copy(
            update={"company": "Apple", "role": "iOS Developer"}
        )
        assert delivery_folder_name(analysis) == "Apple-iOSDeveloper"

    def test_an_unnamed_company_leaves_the_role_alone(self):
        # Plenty of postings never name the employer, and a placeholder
        # standing where a company should be is worse than no company.
        analysis = make_job_analysis().model_copy(
            update={"company": None, "role": "Backend Engineer"}
        )
        assert delivery_folder_name(analysis) == "BackendEngineer"


class TestDelivery:
    def test_the_resume_is_filed_under_company_and_role(self, config_file, tmp_path):
        stub = stub_pipeline(result=compiled_result(tmp_path / "run" / "resume.pdf"))
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(tmp_path / "resumes"),
            )

        delivered = tmp_path / "resumes" / "Globex-BackendEngineer" / "Resume.pdf"
        assert result.exit_code == 0
        assert delivered.is_file()
        assert str(delivered) in result.stdout

    def test_the_artifacts_travel_with_the_resume(self, config_file, tmp_path):
        # Everything the run produced lands one directory below the resume.
        pdf = tmp_path / "run" / "resume.pdf"
        stub = stub_pipeline(result=compiled_result(pdf))
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(tmp_path / "resumes"),
            )

        artifacts = tmp_path / "resumes" / "Globex-BackendEngineer" / "artifacts"
        assert result.exit_code == 0
        assert (artifacts / "resume.pdf").is_file()
        for name in ("report.md", "changes.md", "report.json"):
            assert (artifacts / name).is_file()
            assert str(artifacts / name) in result.stdout
        assert str(artifacts) in result.stdout

    def test_the_working_directory_does_not_survive_a_delivery(
        self, config_file, tmp_path
    ):
        # A move, not a copy: two copies of a run is how a workspace fills up
        # with directories nobody can tell apart.
        stub = stub_pipeline(result=compiled_result(tmp_path / "run" / "resume.pdf"))
        with patch("src.cli.tailor.ResumePipeline", stub):
            invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(tmp_path / "resumes"),
            )
        assert not (tmp_path / "run").exists()

    def test_a_failed_run_keeps_its_working_directory(self, config_file, tmp_path):
        # The artifacts are the diagnosis, and the failure message points at
        # them. Nothing is delivered, so nothing may be moved either.
        stub = stub_pipeline(
            result=compiled_result(
                tmp_path / "run" / "resume.pdf", quality=failing_result()
            )
        )
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(tmp_path / "resumes"),
            )
        assert result.exit_code == 1
        assert (tmp_path / "run" / "report.md").is_file()

    def test_a_second_resume_for_the_same_role_does_not_overwrite_the_first(
        self, config_file, tmp_path
    ):
        for index in ("one", "two"):
            stub = stub_pipeline(result=compiled_result(tmp_path / index / "resume.pdf"))
            with patch("src.cli.tailor.ResumePipeline", stub):
                outcome = invoke(
                    config_file,
                    "--resume",
                    str(CANONICAL),
                    "--jd",
                    str(jd_file(tmp_path)),
                    "--output",
                    str(tmp_path / index),
                    "--deliver-to",
                    str(tmp_path / "resumes"),
                )
            assert outcome.exit_code == 0

        root = tmp_path / "resumes"
        assert (root / "Globex-BackendEngineer" / "Resume.pdf").is_file()
        assert (root / "Globex-BackendEngineer-2" / "Resume.pdf").is_file()

    def test_a_failed_run_is_not_delivered(self, config_file, tmp_path):
        # The delivery directory holds resumes that are ready to send.
        stub = stub_pipeline(
            result=compiled_result(
                tmp_path / "run" / "resume.pdf", quality=failing_result()
            )
        )
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(tmp_path / "resumes"),
            )
        assert result.exit_code == 1
        assert not (tmp_path / "resumes").exists()

    def test_the_default_root_is_read_at_call_time_not_at_import(
        self, config_file, tmp_path, delivery_root
    ):
        # A run without --deliver-to must land under the resolved default.
        # Freezing that default into the Typer signature at import time put
        # eight directories of scripted test output into the real resumes
        # folder, and made the mistake impossible to fence off in a fixture.
        stub = stub_pipeline(result=compiled_result(tmp_path / "run" / "resume.pdf"))
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
            )
        assert result.exit_code == 0
        assert (delivery_root / "Globex-BackendEngineer" / "Resume.pdf").is_file()

    def test_an_unwritable_destination_does_not_fail_the_run(
        self, config_file, tmp_path
    ):
        # The resume exists by this point; a filing problem is a warning.
        blocked = tmp_path / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        stub = stub_pipeline(result=compiled_result(tmp_path / "run" / "resume.pdf"))
        with patch("src.cli.tailor.ResumePipeline", stub):
            result = invoke(
                config_file,
                "--resume",
                str(CANONICAL),
                "--jd",
                str(jd_file(tmp_path)),
                "--output",
                str(tmp_path / "run"),
                "--deliver-to",
                str(blocked),
            )
        assert result.exit_code == 0
        assert "Could not file the run" in result.stdout
        # The artifacts are still somewhere, and the message says where.
        assert str(tmp_path / "run") in result.stdout
        assert (tmp_path / "run" / "report.md").is_file()
        assert "Done." in result.stdout
