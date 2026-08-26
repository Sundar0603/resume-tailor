"""
Renderer package.

Turns a ``Resume`` object into a document: canonical Markdown, or a complete
LaTeX source document built from a frozen template. PDF compilation will join
them here.
"""

from .exceptions import RendererError, RenderingError, SerializationError
from .latex_renderer import (
    DEFAULT_OUTPUT_DIRECTORY,
    DEFAULT_TEMPLATE_DIRECTORY,
    REQUIRED_PLACEHOLDERS,
    LatexRenderer,
)
from .markdown_serializer import SEPARATOR, MarkdownSerializer

__all__ = [
    # Serializer
    "MarkdownSerializer",
    "SEPARATOR",
    # LaTeX renderer
    "LatexRenderer",
    "REQUIRED_PLACEHOLDERS",
    "DEFAULT_TEMPLATE_DIRECTORY",
    "DEFAULT_OUTPUT_DIRECTORY",
    # Exceptions
    "RendererError",
    "RenderingError",
    "SerializationError",
]
