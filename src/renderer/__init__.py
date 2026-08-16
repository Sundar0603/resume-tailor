"""
Renderer package.

Turns a ``Resume`` object into a document. Today that means canonical
Markdown; LaTeX and PDF rendering will join it here.
"""

from .exceptions import RendererError, SerializationError
from .markdown_serializer import SEPARATOR, MarkdownSerializer

__all__ = [
    # Serializer
    "MarkdownSerializer",
    "SEPARATOR",
    # Exceptions
    "RendererError",
    "SerializationError",
]
