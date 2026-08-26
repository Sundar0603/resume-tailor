"""
Models returned by the PDF Compiler.

Pydantic v2 with ``extra="forbid"`` and ``validate_assignment=True``, matching
every other model package in ``src/``.
"""

from pydantic import BaseModel, ConfigDict, Field


class CompilationResult(BaseModel):
    """
    Where a successful compilation put its artifacts, and what it cost.

    There is deliberately no ``success`` field. The compiler raises on every
    failure, so an instance of this model can only ever describe a compilation
    that worked and the flag would be ``True`` on every object that can exist.
    Failure diagnostics travel on
    :class:`~src.compiler.exceptions.CompilationFailedError` instead.

    Paths are ``str`` rather than ``pathlib.Path``: no Pydantic model in this
    codebase holds a ``Path``, which appears only as a constructor, local or
    return type.

    Attributes
    ----------
    pdf_path : str
        The compiled PDF, verified to exist and to be readable.
    log_path : str
        The compiler log. Preserved for every attempt, successful or not.
    tex_path : str
        The LaTeX source exactly as handed to the compiler.
    engine : str
        The resolved engine executable, after PATH lookup.
    exit_code : int
        The engine's exit status. Always 0 here, kept because the Quality Gate
        reports it alongside the log.
    duration_seconds : float
        Wall-clock time spent in the engine.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    pdf_path: str = Field(min_length=1)
    log_path: str = Field(min_length=1)
    tex_path: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    exit_code: int
    duration_seconds: float = Field(ge=0.0)
