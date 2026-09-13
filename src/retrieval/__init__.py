"""Knowledge Base retrieval — canonical evidence selection for one job."""

from .assemble import build_source_resume
from .exceptions import (
    EmptyKnowledgeBase,
    InsufficientCanonicalData,
    RetrievalError,
)
from .models import (
    KnowledgeBaseRetrieval,
    RetrievedEntity,
    RetrievedHighlight,
)
from .retriever import KnowledgeBaseRetriever

__all__ = [
    "KnowledgeBaseRetriever",
    "KnowledgeBaseRetrieval",
    "RetrievedEntity",
    "RetrievedHighlight",
    "build_source_resume",
    "RetrievalError",
    "EmptyKnowledgeBase",
    "InsufficientCanonicalData",
]
