"""
Exceptions raised by the renderer package.

Mirrors the analyzer, planner and generator trees: one package base class,
flat subclasses, docstring-only bodies.
"""


class RendererError(Exception):
    """Base class for every renderer failure."""


class SerializationError(RendererError):
    """
    The Resume holds a value that cannot be expressed in canonical Markdown.

    Raised rather than silently emitting output the parser would misread —
    for example a highlight containing a newline, an empty bullet (which
    truncates the rest of its list on re-parse), or a line consisting only of
    '---' (which the parser treats as a separator and discards).

    Resume *validity* is the Validator's job. This exception covers only the
    narrower question of whether a value survives the Markdown round trip.
    """


class RenderingError(RendererError):
    """
    The Resume cannot be rendered into the selected LaTeX template.

    Raised rather than emitting a document that would not compile, or one that
    is quietly incomplete — a missing or unreadable template, a template that
    does not declare a required placeholder, a section the template wraps in a
    list environment that has no entries, or a character with no LaTeX
    representation.

    As with SerializationError, Resume *validity* is the Validator's job.
    """
