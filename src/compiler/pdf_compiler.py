"""
PDFCompiler — compiles a complete LaTeX document into a PDF.

Takes LaTeX source and produces compilation artifacts. It knows nothing about
resumes, plans or job descriptions, never modifies the source it is given, and
makes no quality judgement: whether the result is one page, well spaced or free
of overfull boxes is the Quality Gate's business. This module answers exactly
one question — did the engine produce a readable PDF?

Every compilation runs in its own temporary directory. That single choice is
what makes concurrent compiles safe, keeps auxiliary files out of the project
tree, and makes "no state from a previous attempt survives" true by
construction rather than by cleanup. Artifacts are copied into the
caller-owned output directory afterwards; the caller owns attempt numbering and
final naming.

The compiler raises on every failure and preserves the ``.tex`` and ``.log``
before it does, so a failed attempt is always debuggable.

Deterministic. ``SOURCE_DATE_EPOCH`` and ``FORCE_SOURCE_DATE`` are pinned in
the engine's environment, without which pdflatex stamps the current time into
``/CreationDate`` and derives the document ``/ID`` from it — identical source
would then produce byte-different PDFs on every run.

Single pass, deliberately. These templates use no ``\\ref``, no
``\\tableofcontents`` and no hyperref bookmarks, so a second run cannot change
the output. Acting on a "Rerun to get ... right" request in the log would be a
quality decision and belongs to the Quality Gate.

No retries, matching the rest of ``src/``.
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .exceptions import (
    CompilationFailedError,
    CompilationTimeoutError,
    InvalidCompilationRequest,
    LatexEngineNotFoundError,
    PDFNotGeneratedError,
)
from .models import CompilationResult

DEFAULT_LATEX_ENGINE = "pdflatex"
DEFAULT_ARTIFACT_DIRECTORY = "output/compile"
DEFAULT_JOB_NAME = "resume"
DEFAULT_TIMEOUT_SECONDS = 120

TEX_SUFFIX = ".tex"
PDF_SUFFIX = ".pdf"
LOG_SUFFIX = ".log"

# Flags every invocation carries.
#   nonstopmode      never block waiting for terminal input
#   halt-on-error    stop at the first error, so the log ends at the cause
#   file-line-error  emit 'file:line: message', which the Quality Gate can parse
#   no-shell-escape  disable \write18
ENGINE_FLAGS = (
    "-interaction=nonstopmode",
    "-halt-on-error",
    "-file-line-error",
    "-no-shell-escape",
)

# A PDF begins with these bytes. Checking them is what "readable as a file"
# means here: a truncated or half-written file fails, and no PDF library is
# needed to find out.
PDF_MAGIC = b"%PDF-"

# runner(argv, cwd, timeout, env) -> (exit_code, output)
_Runner = Callable[[List[str], str, int, Dict[str, str]], Tuple[int, str]]

# Pinned so that identical source compiles to identical bytes.
DETERMINISTIC_ENVIRONMENT = {
    "SOURCE_DATE_EPOCH": "0",
    "FORCE_SOURCE_DATE": "1",
}


class PDFCompiler:
    """
    Compiles LaTeX source into a PDF using a configurable engine.

    Stateless: every call is independent, and nothing the caller passes in is
    modified.

    Parameters
    ----------
    engine : str
        Executable to invoke. Resolved through ``PATH``; an absolute or
        relative path to an executable file is also accepted, which is how a
        TinyTeX installation that is not on ``PATH`` can still be used.
    timeout_seconds : int
        Kill the engine after this long. A hung compile would otherwise
        consume the whole run budget.
    runner : callable, optional
        Injection point used by the tests to drive every branch without a
        mocking library. Called as ``runner(argv, cwd, timeout, env)`` and
        expected to return ``(exit_code, output)`` or raise
        ``subprocess.TimeoutExpired``.
    """

    def __init__(
        self,
        engine: str = DEFAULT_LATEX_ENGINE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        runner: Optional[_Runner] = None,
    ) -> None:
        self._engine = engine
        self._timeout_seconds = timeout_seconds
        self._runner = runner if runner is not None else _run_subprocess

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile(
        self,
        latex_source: str,
        output_directory: str = DEFAULT_ARTIFACT_DIRECTORY,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> CompilationResult:
        """
        Compile a complete LaTeX document and preserve its artifacts.

        Parameters
        ----------
        latex_source : str
            A complete document, from ``\\documentclass`` to ``\\end{document}``.
            Written out verbatim; never modified or repaired.
        output_directory : str
            Directory to copy artifacts into. Created if it does not exist. The
            caller owns this path and the attempt naming it encodes.
        job_name : str
            Base name for the ``.tex``, ``.pdf`` and ``.log`` files.

        Returns
        -------
        CompilationResult
            Paths to the PDF, log and source, plus the engine and timing.

        Raises
        ------
        LatexEngineNotFoundError
            The engine is neither on PATH nor an executable file.
        CompilationTimeoutError
            The engine did not finish within ``timeout_seconds``.
        PDFNotGeneratedError
            The engine succeeded but produced no readable PDF.
        CompilationFailedError
            The engine exited non-zero.
        """
        engine = self._resolve_engine()
        self._require_job_name(job_name)
        destination = Path(output_directory)
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="resume-tailor-compile-") as workspace:
            return self._compile_in(
                Path(workspace), engine, latex_source, destination, job_name
            )

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def _compile_in(
        self,
        workspace: Path,
        engine: str,
        latex_source: str,
        destination: Path,
        job_name: str,
    ) -> CompilationResult:
        """Run one compilation inside an already-isolated workspace."""
        source = workspace / (job_name + TEX_SUFFIX)
        source.write_text(latex_source, encoding="utf-8")
        argv = [engine] + list(ENGINE_FLAGS) + [source.name]

        started = time.monotonic()
        timed_out = False
        exit_code = None
        try:
            exit_code, output = self._runner(
                argv, str(workspace), self._timeout_seconds, self._environment()
            )
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            output = _decode(expired.output)
        except OSError as unusable:
            # The engine resolved but could not be executed: the exec bit is set
            # on something that is not a binary, or it vanished between
            # resolution and launch. No process ran, so there is no log.
            raise LatexEngineNotFoundError(
                "LaTeX engine '{0}' could not be executed.\n\n"
                "  {1}".format(engine, unusable)
            )
        duration = time.monotonic() - started

        # Preserve before judging: the log is the only evidence a failed
        # attempt leaves behind, and the workspace is about to be deleted.
        tex_path, log_path = self._preserve(workspace, destination, job_name, output)

        self._raise_for_process(timed_out, exit_code, log_path, tex_path)

        pdf = self._verify_pdf(workspace / (job_name + PDF_SUFFIX), log_path, tex_path)
        pdf_path = shutil.copy2(str(pdf), str(destination / pdf.name))
        return CompilationResult(
            pdf_path=str(pdf_path),
            log_path=log_path,
            tex_path=tex_path,
            engine=engine,
            exit_code=exit_code,
            duration_seconds=duration,
        )

    def _raise_for_process(
        self,
        timed_out: bool,
        exit_code: Optional[int],
        log_path: str,
        tex_path: str,
    ) -> None:
        """Turn a timeout or a non-zero exit into the matching exception."""
        if timed_out:
            raise CompilationTimeoutError(
                _message(
                    "LaTeX compilation timed out after "
                    "{0} seconds.".format(self._timeout_seconds),
                    None,
                    log_path,
                ),
                None,
                log_path,
                tex_path,
            )
        if exit_code != 0:
            raise CompilationFailedError(
                _message("LaTeX compilation failed.", exit_code, log_path),
                exit_code,
                log_path,
                tex_path,
            )

    def _preserve(
        self, workspace: Path, destination: Path, job_name: str, output: str
    ) -> Tuple[str, str]:
        """
        Copy the source and log out of the workspace.

        The engine's own ``.log`` is the useful one and is preferred. When the
        engine died before writing it, the captured stdout is written to the
        same path instead, so ``log_path`` always names a file that exists.
        """
        source = workspace / (job_name + TEX_SUFFIX)
        tex_target = destination / source.name
        shutil.copy2(str(source), str(tex_target))

        log = workspace / (job_name + LOG_SUFFIX)
        log_target = destination / (job_name + LOG_SUFFIX)
        if log.is_file():
            shutil.copy2(str(log), str(log_target))
        else:
            log_target.write_text(output, encoding="utf-8")
        return str(tex_target), str(log_target)

    def _verify_pdf(self, pdf: Path, log_path: str, tex_path: str) -> Path:
        """Check that the engine actually produced a readable PDF."""
        if not pdf.is_file():
            reason = "no PDF was produced"
        elif pdf.stat().st_size == 0:
            reason = "the PDF is empty"
        elif not _has_pdf_magic(pdf):
            reason = "the PDF is not readable"
        else:
            return pdf
        raise PDFNotGeneratedError(
            _message(
                "LaTeX reported success but {0}.".format(reason), 0, log_path
            ),
            0,
            log_path,
            tex_path,
        )

    # ------------------------------------------------------------------
    # Engine and environment
    # ------------------------------------------------------------------

    def _resolve_engine(self) -> str:
        """Locate the configured engine executable."""
        return resolve_engine(self._engine)

    @staticmethod
    def _environment() -> Dict[str, str]:
        """The engine's environment, with the determinism knobs pinned."""
        environment = os.environ.copy()
        environment.update(DETERMINISTIC_ENVIRONMENT)
        return environment

    @staticmethod
    def _require_job_name(job_name: str) -> None:
        """Reject a job name that is empty or would escape the workspace."""
        if not job_name.strip():
            raise InvalidCompilationRequest("job_name must not be empty.")
        if os.sep in job_name or (os.altsep and os.altsep in job_name):
            raise InvalidCompilationRequest(
                "job_name must be a bare file name, not a path: "
                "{0!r}".format(job_name)
            )


# ----------------------------------------------------------------------
# Module helpers
# ----------------------------------------------------------------------


def resolve_engine(engine: str) -> str:
    """
    Locate a LaTeX engine executable.

    Tries ``PATH`` first, then treats the value as a path to an executable. The
    second branch matters: a TinyTeX install is often absent from ``PATH`` in a
    non-login shell.

    Public so that ``resume-tailor doctor`` can report the toolchain without
    duplicating the lookup or reaching into a private method.

    Parameters
    ----------
    engine : str
        Executable name or path.

    Returns
    -------
    str
        The resolved absolute path.

    Raises
    ------
    LatexEngineNotFoundError
        The engine is neither on PATH nor an executable file.
    """
    located = shutil.which(engine)
    if located:
        return located
    candidate = Path(engine)
    if candidate.is_file() and os.access(str(candidate), os.X_OK):
        return str(candidate)
    raise LatexEngineNotFoundError(
        "LaTeX engine '{0}' was not found.\n\n"
        "Install a TeX distribution, or pass an executable path as the "
        "engine.".format(engine)
    )


def _run_subprocess(
    argv: List[str], cwd: str, timeout: int, env: Dict[str, str]
) -> Tuple[int, str]:
    """Invoke the engine, folding stderr into stdout. The default runner."""
    completed = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        env=env,
    )
    return completed.returncode, _decode(completed.stdout)


def _decode(output) -> str:
    """Decode captured process output, which may be bytes, str or None."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", "replace")
    return output


def _has_pdf_magic(pdf: Path) -> bool:
    """Whether a file begins with the PDF magic bytes."""
    with pdf.open("rb") as handle:
        return handle.read(len(PDF_MAGIC)) == PDF_MAGIC


def _message(headline: str, exit_code: Optional[int], log_path: str) -> str:
    """Build a diagnostic a user can act on without reading a traceback."""
    lines = [headline, ""]
    if exit_code is not None:
        lines.extend(["Exit code: {0}".format(exit_code), ""])
    lines.extend(["See:", log_path])
    return "\n".join(lines)
