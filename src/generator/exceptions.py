"""
Exceptions raised by the Resume Generator.

Mirrors the analyzer and planner trees: one package base class, flat
subclasses, docstring-only bodies. No provider SDK error ever reaches a
caller — transport failures are wrapped in :class:`GeneratorError`.
"""


class GeneratorError(Exception):
    """Base class for every Resume Generator failure."""


class InvalidGeneratorResponse(GeneratorError):
    """The model returned nothing usable, or a response the schema rejects."""


class InvalidGeneratorJSON(GeneratorError):
    """The model's response contained no parseable JSON object."""


class GeneratorResponseValidationError(GeneratorError):
    """The assembled resume failed ResumeValidator."""


class GenerationConstraintError(GeneratorError):
    """
    The generated content broke a rule the validator cannot see.

    Covers strict-mode fabrication (a technology, skill or metric absent from
    the source resume) and structural floors the plan would breach, such as
    removing so many projects that fewer than two remain.
    """
