"""
Exception hierarchy for the Knowledge Base package.

One base class and flat subclasses, matching the house convention used by
``src/planner/exceptions.py`` and ``src/analyzer/exceptions.py``. Bodies are
docstring-only: the message carries the detail.
"""


class KnowledgeBaseError(Exception):
    """Base class for every Knowledge Base failure."""


class KnowledgeBaseNotFoundError(KnowledgeBaseError):
    """The Knowledge Base file does not exist at the given path."""


class MissingKnowledgeSection(KnowledgeBaseError):
    """A required top-level section is absent from the Knowledge Base."""


class MissingEntityId(KnowledgeBaseError):
    """A Knowledge Base entity block carries no ``Id:`` line.

    Knowledge Base ids are stable across runs and therefore authoritative:
    they are read from the file, never derived from block order. A block
    without one cannot be referenced by retrieval or lineage.
    """


class DuplicateEntityId(KnowledgeBaseError):
    """Two Knowledge Base entities of the same kind share an id."""


class MalformedEntityId(KnowledgeBaseError):
    """An id does not match the ``{prefix}_{number}`` convention for its kind."""


class WrappedBullet(KnowledgeBaseError):
    """A bullet was wrapped onto a continuation line.

    ``get_list`` stops at the first non-bullet, non-blank line, so a wrapped
    bullet silently discards every later bullet in that list — the failure
    PROJECT_KNOWLEDGE §10c records. The Knowledge Base is hand-maintained and
    holds bullets 60 words long, which is exactly where someone reaches for a
    line break, so the truncation is made loud here rather than left silent.
    """
