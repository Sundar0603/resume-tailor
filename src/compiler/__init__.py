"""
Compiler package.

Turns a complete LaTeX document into a PDF by invoking a TeX engine in an
isolated working directory, and preserves the artifacts of every attempt.
Whether the resulting PDF is *good* is the Quality Gate's question, not this
package's.
"""

from .exceptions import (
    CompilationFailedError,
    CompilationTimeoutError,
    CompilerError,
    InvalidCompilationRequest,
    LatexEngineNotFoundError,
    PDFNotGeneratedError,
)
from .models import CompilationResult
from .pdf_compiler import (
    DEFAULT_ARTIFACT_DIRECTORY,
    DEFAULT_JOB_NAME,
    DEFAULT_LATEX_ENGINE,
    DEFAULT_TIMEOUT_SECONDS,
    ENGINE_FLAGS,
    PDFCompiler,
    resolve_engine,
)

__all__ = [
    # Compiler
    "PDFCompiler",
    "ENGINE_FLAGS",
    "resolve_engine",
    "DEFAULT_LATEX_ENGINE",
    "DEFAULT_ARTIFACT_DIRECTORY",
    "DEFAULT_JOB_NAME",
    "DEFAULT_TIMEOUT_SECONDS",
    # Result
    "CompilationResult",
    # Exceptions
    "CompilerError",
    "InvalidCompilationRequest",
    "LatexEngineNotFoundError",
    "CompilationFailedError",
    "PDFNotGeneratedError",
    "CompilationTimeoutError",
]
