"""
Stable identifiers for Knowledge Base content.

Two kinds of id live in this project and they must not be confused.

*Runtime ids* (``src/entity_ids.py``) are positional and regenerated on every
parse. They exist so the Planner, Generator and Revision Engine can reference
entities within a single run. They are deliberately not stable across runs.

*Knowledge Base ids* are the opposite: they identify a canonical fact for as
long as that fact exists, so retrieval results, lineage and reports stay
comparable between runs. Entity ids are written into the file by hand and read
back verbatim.

Highlight ids are the one exception, and they are derived rather than written.
A highlight is a sentence, not a block, so giving each one a hand-maintained
``Id:`` line would be unreadable in a file the user edits directly. Deriving the
id from the *content* keeps it stable across runs and across reordering — the
property task 020 asks for when it says an id must not depend on the order a
parser happened to discover things in. The cost is that editing a bullet's
wording mints a new id, which is correct: a reworded fact is a different string,
and nothing persists these ids between runs anyway.
"""

import hashlib
import re
from typing import Iterable

from src.vocabulary import normalise

#: Number of hex characters kept from the digest. Eight gives 4.3 billion
#: values against a Knowledge Base holding tens of highlights, so a collision
#: would need a deliberate effort to construct.
HIGHLIGHT_DIGEST_LENGTH = 8

#: Separator between the owning entity's id and the highlight digest.
HIGHLIGHT_SEPARATOR = ".h_"

#: Matches ``{prefix}_{digits}`` — the shape every Knowledge Base entity id has.
ENTITY_ID_PATTERN = re.compile(r"^(?P<prefix>[a-z]+)_(?P<number>\d+)$")


def highlight_id(entity_id: str, text: str) -> str:
    """
    Return the stable id of one highlight belonging to ``entity_id``.

    Derived from the normalised text, so whitespace and case changes do not
    mint a new id but a genuine rewording does.

    >>> highlight_id("exp_001", "Built a thing")
    'exp_001.h_29981ef3'
    """
    digest = hashlib.sha1(normalise(text).encode("utf-8")).hexdigest()
    return "{0}{1}{2}".format(
        entity_id, HIGHLIGHT_SEPARATOR, digest[:HIGHLIGHT_DIGEST_LENGTH]
    )


def highlight_ids(entity_id: str, highlights: Iterable[str]) -> list:
    """Return the stable ids of every highlight belonging to ``entity_id``."""
    return [highlight_id(entity_id, text) for text in highlights]


def owning_entity_id(highlight_identifier: str) -> str:
    """
    Return the entity id a highlight id belongs to.

    >>> owning_entity_id("exp_001.h_29981ef3")
    'exp_001'
    """
    return highlight_identifier.split(HIGHLIGHT_SEPARATOR)[0]


def has_expected_prefix(entity_id: str, prefix: str) -> bool:
    """Return True when ``entity_id`` is ``{prefix}_{digits}``."""
    match = ENTITY_ID_PATTERN.match(entity_id.strip())
    return bool(match) and match.group("prefix") == prefix
