"""
Pipeline exceptions.

House style: one package base class, flat subclasses, docstring-only bodies.

The pipeline deliberately does **not** wrap the errors its stages raise. A
``PlannerError`` or a ``CompilationFailedError`` reaching the caller unchanged
is more useful than a generic "pipeline failed", and every stage's exception
tree is already documented. Only failures that belong to the *chaining itself*
live here.
"""


class PipelineError(Exception):
    """Base class for every pipeline error."""


class PipelineStageError(PipelineError):
    """
    A stage was asked to run without the output of the stage before it.

    Guards against a caller assembling a partial run by hand and getting a
    confusing failure three stages later.
    """
