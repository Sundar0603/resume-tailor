"""
Unit tests for the PDF Compiler.

These run with no TeX distribution present: the engine is resolved to a real
executable that is not a TeX engine, and the invocation itself is supplied by a
fake runner. Real compilation is covered by test_compilation_integration.py.
"""

import os

import pytest

from src.compiler import (
    DEFAULT_JOB_NAME,
    ENGINE_FLAGS,
    CompilationFailedError,
    CompilationResult,
    CompilationTimeoutError,
    InvalidCompilationRequest,
    LatexEngineNotFoundError,
    PDFCompiler,
    PDFNotGeneratedError,
)
from src.compiler.pdf_compiler import DETERMINISTIC_ENVIRONMENT

from .conftest import (
    MINIMAL_DOCUMENT,
    RESOLVABLE_ENGINE,
    VALID_PDF_BYTES,
    FakeRunner,
    TimeoutRunner,
    WorkspaceProbe,
)


def make_compiler(runner, engine=RESOLVABLE_ENGINE, timeout_seconds=120):
    """A compiler wired to a fake runner and a resolvable engine."""
    return PDFCompiler(engine=engine, timeout_seconds=timeout_seconds, runner=runner)


class TestSuccessfulCompilation:
    def test_it_returns_a_compilation_result(self, tmp_path):
        result = make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert isinstance(result, CompilationResult)

    def test_the_artifacts_are_written_to_the_output_directory(self, tmp_path):
        result = make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "resume.log",
            "resume.pdf",
            "resume.tex",
        ]
        assert result.pdf_path == str(tmp_path / "resume.pdf")
        assert result.log_path == str(tmp_path / "resume.log")
        assert result.tex_path == str(tmp_path / "resume.tex")

    def test_it_reports_the_engine_and_exit_code(self, tmp_path):
        result = make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert result.engine == RESOLVABLE_ENGINE
        assert result.exit_code == 0
        assert result.duration_seconds >= 0.0

    def test_the_output_directory_is_created_if_absent(self, tmp_path):
        destination = tmp_path / "nested" / "attempt_1"
        make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(destination)
        )
        assert (destination / "resume.pdf").is_file()

    def test_the_pdf_contents_survive_the_copy(self, tmp_path):
        make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert (tmp_path / "resume.pdf").read_bytes() == VALID_PDF_BYTES


class TestTheSourceIsNotModified:
    def test_the_written_tex_is_byte_identical_to_the_input(self, tmp_path):
        make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert (tmp_path / "resume.tex").read_text(encoding="utf-8") == MINIMAL_DOCUMENT

    def test_a_document_with_no_trailing_newline_is_left_alone(self, tmp_path):
        source = MINIMAL_DOCUMENT.rstrip("\n")
        make_compiler(FakeRunner()).compile(source, output_directory=str(tmp_path))
        assert (tmp_path / "resume.tex").read_text(encoding="utf-8") == source


class TestTheInvocation:
    def test_it_calls_the_engine_once_with_every_flag(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        argv = runner.call["argv"]
        assert argv[0] == RESOLVABLE_ENGINE
        for flag in ENGINE_FLAGS:
            assert flag in argv

    def test_it_passes_a_bare_relative_file_name(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert runner.call["argv"][-1] == "resume.tex"

    def test_it_runs_in_a_workspace_that_is_not_the_output_directory(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert runner.call["cwd"] != str(tmp_path)

    def test_it_passes_the_configured_timeout(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner, timeout_seconds=7).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert runner.call["timeout"] == 7

    def test_the_environment_pins_the_determinism_knobs(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        for key, value in DETERMINISTIC_ENVIRONMENT.items():
            assert runner.call["env"][key] == value

    def test_the_environment_still_carries_the_ambient_path(self, tmp_path):
        runner = FakeRunner()
        make_compiler(runner).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert runner.call["env"].get("PATH") == os.environ.get("PATH")


class TestIsolation:
    def test_the_workspace_is_removed_afterwards(self, tmp_path):
        probe = WorkspaceProbe()
        make_compiler(probe).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert not os.path.exists(probe.workspaces[0])

    def test_auxiliary_files_do_not_reach_the_output_directory(self, tmp_path):
        make_compiler(WorkspaceProbe()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert not (tmp_path / "resume.aux").exists()

    def test_two_compilations_use_different_workspaces(self, tmp_path):
        probe = WorkspaceProbe()
        compiler = make_compiler(probe)
        compiler.compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path / "one"))
        compiler.compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path / "two"))
        assert probe.workspaces[0] != probe.workspaces[1]

    def test_repeated_compilations_do_not_interfere(self, tmp_path):
        compiler = make_compiler(FakeRunner())
        for attempt in range(1, 5):
            destination = tmp_path / "attempt_{0}".format(attempt)
            result = compiler.compile(
                MINIMAL_DOCUMENT, output_directory=str(destination)
            )
            assert result.pdf_path == str(destination / "resume.pdf")

    def test_a_failure_does_not_poison_the_next_compilation(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            make_compiler(FakeRunner(exit_code=1, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path / "bad")
            )
        result = make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path / "good")
        )
        assert result.exit_code == 0


class TestJobName:
    def test_it_names_every_artifact(self, tmp_path):
        make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path), job_name="attempt_2"
        )
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "attempt_2.log",
            "attempt_2.pdf",
            "attempt_2.tex",
        ]

    def test_the_default_is_resume(self, tmp_path):
        result = make_compiler(FakeRunner()).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert result.pdf_path.endswith(DEFAULT_JOB_NAME + ".pdf")

    def test_an_empty_job_name_is_rejected(self, tmp_path):
        with pytest.raises(InvalidCompilationRequest):
            make_compiler(FakeRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path), job_name="  "
            )

    def test_a_job_name_containing_a_separator_is_rejected(self, tmp_path):
        with pytest.raises(InvalidCompilationRequest):
            make_compiler(FakeRunner()).compile(
                MINIMAL_DOCUMENT,
                output_directory=str(tmp_path),
                job_name="../escape",
            )

    def test_a_rejected_job_name_starts_no_process(self, tmp_path):
        runner = FakeRunner()
        with pytest.raises(InvalidCompilationRequest):
            make_compiler(runner).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path), job_name=""
            )
        assert runner.calls == []


class TestEngineResolution:
    def test_an_unknown_engine_raises(self):
        with pytest.raises(LatexEngineNotFoundError):
            PDFCompiler(engine="definitely-not-an-engine", runner=FakeRunner()).compile(
                MINIMAL_DOCUMENT
            )

    def test_an_unknown_engine_starts_no_process(self):
        runner = FakeRunner()
        with pytest.raises(LatexEngineNotFoundError):
            PDFCompiler(engine="definitely-not-an-engine", runner=runner).compile(
                MINIMAL_DOCUMENT
            )
        assert runner.calls == []

    def test_an_unknown_engine_creates_no_output_directory(self, tmp_path):
        destination = tmp_path / "never"
        with pytest.raises(LatexEngineNotFoundError):
            PDFCompiler(engine="definitely-not-an-engine", runner=FakeRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(destination)
            )
        assert not destination.exists()

    def test_an_absolute_path_to_an_executable_is_accepted(self, tmp_path):
        result = make_compiler(FakeRunner(), engine=RESOLVABLE_ENGINE).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert result.engine == RESOLVABLE_ENGINE

    def test_a_path_to_a_non_executable_file_raises(self, tmp_path):
        not_executable = tmp_path / "not-an-engine"
        not_executable.write_text("#!/bin/sh\n", encoding="utf-8")
        not_executable.chmod(0o644)
        with pytest.raises(LatexEngineNotFoundError):
            PDFCompiler(engine=str(not_executable), runner=FakeRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path / "out")
            )

    def test_a_name_on_path_resolves_to_an_absolute_path(self, tmp_path):
        import shutil

        if shutil.which("sh") is None:
            pytest.skip("sh is not on PATH")
        result = make_compiler(FakeRunner(), engine="sh").compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert os.path.isabs(result.engine)


class TestNonZeroExit:
    def test_it_raises(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            make_compiler(FakeRunner(exit_code=1, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_a_pdf_written_alongside_a_failure_is_not_accepted(self, tmp_path):
        # nonstopmode routinely writes a partial PDF and still exits non-zero.
        with pytest.raises(CompilationFailedError):
            make_compiler(FakeRunner(exit_code=1, write_pdf=True)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_the_exception_carries_the_diagnostics(self, tmp_path):
        try:
            make_compiler(FakeRunner(exit_code=3, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        except CompilationFailedError as exc:
            assert exc.exit_code == 3
            assert exc.log_path == str(tmp_path / "resume.log")
            assert exc.tex_path == str(tmp_path / "resume.tex")
        else:
            raise AssertionError("expected CompilationFailedError")

    def test_the_message_names_the_exit_code_and_the_log(self, tmp_path):
        try:
            make_compiler(FakeRunner(exit_code=1, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        except CompilationFailedError as exc:
            message = str(exc)
            assert "Exit code: 1" in message
            assert str(tmp_path / "resume.log") in message
        else:
            raise AssertionError("expected CompilationFailedError")

    def test_no_pdf_is_copied_out(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            make_compiler(FakeRunner(exit_code=1, write_pdf=True)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        assert not (tmp_path / "resume.pdf").exists()


class TestMissingOrUnreadablePDF:
    def test_a_missing_pdf_raises(self, tmp_path):
        with pytest.raises(PDFNotGeneratedError):
            make_compiler(FakeRunner(exit_code=0, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_an_empty_pdf_raises(self, tmp_path):
        with pytest.raises(PDFNotGeneratedError):
            make_compiler(FakeRunner(pdf_bytes=b"")).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_a_file_without_the_pdf_magic_raises(self, tmp_path):
        with pytest.raises(PDFNotGeneratedError):
            make_compiler(FakeRunner(pdf_bytes=b"not a pdf at all")).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_it_is_a_compilation_failure(self, tmp_path):
        # A caller that does not care why should be able to catch one class.
        with pytest.raises(CompilationFailedError):
            make_compiler(FakeRunner(exit_code=0, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_the_log_is_still_preserved(self, tmp_path):
        with pytest.raises(PDFNotGeneratedError):
            make_compiler(FakeRunner(exit_code=0, write_pdf=False)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        assert (tmp_path / "resume.log").is_file()
        assert (tmp_path / "resume.tex").is_file()


class TestTimeout:
    def test_it_raises(self, tmp_path):
        with pytest.raises(CompilationTimeoutError):
            make_compiler(TimeoutRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_it_is_a_compilation_failure(self, tmp_path):
        with pytest.raises(CompilationFailedError):
            make_compiler(TimeoutRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )

    def test_the_artifacts_are_preserved(self, tmp_path):
        with pytest.raises(CompilationTimeoutError):
            make_compiler(TimeoutRunner()).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        assert (tmp_path / "resume.tex").is_file()
        assert (tmp_path / "resume.log").is_file()

    def test_the_partial_output_becomes_the_log(self, tmp_path):
        with pytest.raises(CompilationTimeoutError):
            make_compiler(TimeoutRunner(output=b"killed mid-run\n")).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        assert "killed mid-run" in (tmp_path / "resume.log").read_text(encoding="utf-8")

    def test_the_engine_log_wins_when_one_was_written(self, tmp_path):
        with pytest.raises(CompilationTimeoutError):
            make_compiler(TimeoutRunner(write_log=True)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        assert (tmp_path / "resume.log").read_text(encoding="utf-8") == "partial log\n"

    def test_the_message_names_the_timeout(self, tmp_path):
        try:
            make_compiler(TimeoutRunner(), timeout_seconds=9).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path)
            )
        except CompilationTimeoutError as exc:
            assert "9 seconds" in str(exc)
            assert exc.exit_code is None
            assert exc.log_path == str(tmp_path / "resume.log")
        else:
            raise AssertionError("expected CompilationTimeoutError")


class TestLogCapture:
    def test_the_engine_log_is_preferred(self, tmp_path):
        make_compiler(FakeRunner(log_text="the real log\n")).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert (tmp_path / "resume.log").read_text(encoding="utf-8") == "the real log\n"

    def test_captured_output_is_used_when_the_engine_wrote_no_log(self, tmp_path):
        make_compiler(
            FakeRunner(write_log=False, stdout="stdout and stderr together\n")
        ).compile(MINIMAL_DOCUMENT, output_directory=str(tmp_path))
        assert (
            tmp_path / "resume.log"
        ).read_text(encoding="utf-8") == "stdout and stderr together\n"

    def test_a_log_always_exists_at_the_reported_path(self, tmp_path):
        result = make_compiler(FakeRunner(write_log=False)).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert os.path.isfile(result.log_path)


class TestNoQualityJudgement:
    def test_it_does_not_inspect_the_pdf_beyond_readability(self, tmp_path):
        # A one-byte-past-magic PDF is nonsense as a document, but the compiler
        # is not the Quality Gate and must not care.
        result = make_compiler(FakeRunner(pdf_bytes=b"%PDF-1.4\n")).compile(
            MINIMAL_DOCUMENT, output_directory=str(tmp_path)
        )
        assert result.exit_code == 0


class TestAnUnusableEngine:
    """
    The engine resolves but cannot be executed.

    Without this, subprocess raises a bare OSError and the caller gets a raw
    traceback for what is really an engine-configuration problem.
    """

    def _fake_engine(self, tmp_path):
        engine = tmp_path / "fake-engine"
        engine.write_text("this is not a binary\n", encoding="utf-8")
        engine.chmod(0o755)
        return engine

    def test_it_raises_a_compiler_error(self, tmp_path):
        engine = self._fake_engine(tmp_path)
        with pytest.raises(LatexEngineNotFoundError):
            PDFCompiler(engine=str(engine)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path / "out")
            )

    def test_it_does_not_leak_an_oserror(self, tmp_path):
        engine = self._fake_engine(tmp_path)
        try:
            PDFCompiler(engine=str(engine)).compile(
                MINIMAL_DOCUMENT, output_directory=str(tmp_path / "out")
            )
        except LatexEngineNotFoundError as exc:
            assert "could not be executed" in str(exc)
        except OSError:
            raise AssertionError("a raw OSError reached the caller")
        else:
            raise AssertionError("expected LatexEngineNotFoundError")
