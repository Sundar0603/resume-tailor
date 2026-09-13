"""Knowledge Base package — the canonical source of truth for career facts."""

from .exceptions import (
    DuplicateEntityId,
    KnowledgeBaseError,
    KnowledgeBaseNotFoundError,
    MalformedEntityId,
    MissingEntityId,
    MissingKnowledgeSection,
    WrappedBullet,
)
from .identifiers import (
    HIGHLIGHT_SEPARATOR,
    highlight_id,
    highlight_ids,
    owning_entity_id,
)
from .knowledge_parser import KnowledgeBaseParser
from .models import (
    SUMMARY_PREFIX,
    CanonicalSummary,
    KnowledgeBase,
    KnowledgeMetadata,
)

__all__ = [
    "KnowledgeBase",
    "KnowledgeBaseParser",
    "KnowledgeMetadata",
    "CanonicalSummary",
    "SUMMARY_PREFIX",
    "highlight_id",
    "highlight_ids",
    "owning_entity_id",
    "HIGHLIGHT_SEPARATOR",
    "KnowledgeBaseError",
    "KnowledgeBaseNotFoundError",
    "MissingKnowledgeSection",
    "MissingEntityId",
    "DuplicateEntityId",
    "MalformedEntityId",
    "WrappedBullet",
]
