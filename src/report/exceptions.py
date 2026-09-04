"""
Reporter exceptions.

House style: one package base class, flat subclasses, docstring-only bodies.

There is deliberately almost nothing here. The Reporter reads structured
results that every upstream stage has already validated, makes no network call,
runs no subprocess and asks no model anything, so the only way it can fail is
to be handed a result it cannot describe. It never reports a *judgement* of its
own -- a resume that failed the Quality Gate is a report saying so, not an
exception.
"""


class ReportError(Exception):
    """Base class for every Reporter error."""


class IncompleteRunError(ReportError):
    """
    The run carries no Quality Gate verdict at all.

    ``PipelineResult.quality`` is ``Optional`` because the model is built once
    at the end of a run, and a caller can construct one by hand. A report with
    no verdict would have to invent one, so it refuses instead.
    """


class ReportWriteError(ReportError):
    """
    The report could not be written to the requested directory.

    Wraps the underlying ``OSError`` so a caller that already handles this
    package's errors does not also have to handle filesystem ones.
    """
