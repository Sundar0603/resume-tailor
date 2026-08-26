"""
Exceptions raised by the PDF Compiler.

Mirrors the analyzer, planner, generator and renderer trees: one package base
class and a shallow set of subclasses. No ``subprocess`` error ever reaches a
caller — a missing engine, a non-zero exit and a timeout are all reported as
compiler exceptions.

One deliberate divergence from the house style. Every other exception in this
codebase has a docstring-only body; :class:`CompilationFailedError` carries
``exit_code``, ``log_path`` and ``tex_path`` as attributes. The compiler raises
rather than returning a result object, so there is no return value for the
diagnostics to travel on, and the Revision Engine needs the log path to decide
what to do next. Putting them in the message string alone would force callers
to parse prose.
"""

from typing import Optional


class CompilerError(Exception):
    """Base class for every PDF Compiler failure."""


class LatexEngineNotFoundError(CompilerError):
    """
    The configured LaTeX engine could not be located.

    Raised when the engine is neither on ``PATH`` nor an executable file at the
    path given. Carries no log or exit code because no process ever ran.
    """


class InvalidCompilationRequest(CompilerError):
    """
    The caller asked for something the compiler cannot honour.

    Raised before any process starts — an empty job name, or one containing a
    path separator, which would write artifacts outside the isolated
    workspace.
    """


class CompilationFailedError(CompilerError):
    """
    The engine ran and did not deliver a usable PDF.

    Base for every failure that happens after the process starts, so a caller
    that does not care *why* can catch this one class and still reach the log.

    Attributes
    ----------
    exit_code : int or None
        The engine's exit status. ``None`` when the process did not exit
        normally, as on a timeout.
    log_path : str or None
        Path to the preserved compiler log. Always populated in practice —
        artifacts are written before this exception is raised — but optional so
        that a caller constructing one by hand is not forced to invent a path.
    tex_path : str or None
        Path to the preserved LaTeX source that produced the failure.
    """

    def __init__(
        self,
        message: str,
        exit_code: Optional[int] = None,
        log_path: Optional[str] = None,
        tex_path: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.log_path = log_path
        self.tex_path = tex_path


class PDFNotGeneratedError(CompilationFailedError):
    """
    The engine reported success but produced no readable PDF.

    Raised when the expected file is absent, empty, or does not begin with the
    PDF magic bytes. Exiting with status 0 is not by itself evidence that a PDF
    exists: under ``-interaction=nonstopmode`` the engine can also write a
    partial file and exit non-zero, which is why both conditions are checked.
    """


class CompilationTimeoutError(CompilationFailedError):
    """
    The engine did not finish within the configured timeout.

    A resume run has a 180-second budget covering analysis, planning,
    generation, compilation and up to three revisions. A compile that hangs
    would consume all of it, so the process is killed and its artifacts are
    preserved for inspection.
    """
