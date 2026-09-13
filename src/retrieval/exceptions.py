"""
Exception hierarchy for Knowledge Base retrieval.

One base class and flat subclasses with docstring-only bodies, matching the
house convention.
"""


class RetrievalError(Exception):
    """Base class for every retrieval failure."""


class EmptyKnowledgeBase(RetrievalError):
    """The Knowledge Base holds nothing to retrieve from."""


class InsufficientCanonicalData(RetrievalError):
    """The Knowledge Base cannot satisfy the Validator's floors.

    The Validator requires exactly two experiences, at least two projects, at
    least one skill category and at least one education entry. A Knowledge Base
    below any of those cannot produce a valid resume no matter how well
    retrieval scores, so it fails here rather than three stages later with a
    less obvious message.
    """
