"""
Runtime entity ID minting.

Every resume entity carries an ``id`` so that the Planner, Generator, Revision
Engine and Quality Gate can reference it without matching on prose. IDs are
runtime-only: they never appear in the Markdown source and are regenerated on
every parse.

The format is ``{prefix}_{n:03d}``, one-based. Two components mint IDs — the
Parser, which numbers a freshly parsed resume positionally, and the Generator,
which adds IDs for entities that did not exist in the source. Both go through
this module so there is one convention rather than two.
"""

import re
from typing import Iterable, List

#: Prefixes used by the domain models.
SKILL_PREFIX = "skill"
EXPERIENCE_PREFIX = "exp"
PROJECT_PREFIX = "proj"
EDUCATION_PREFIX = "edu"

#: Width of the zero-padded numeric suffix.
ID_WIDTH = 3

_SUFFIX_PATTERN = re.compile(r"^(?P<prefix>.+)_(?P<number>\d+)$")


def format_id(prefix: str, number: int) -> str:
    """
    Return the canonical ID string for a prefix and a one-based number.

    Parameters
    ----------
    prefix:
        Entity prefix, e.g. ``"proj"``.
    number:
        One-based position. Numbers wider than :data:`ID_WIDTH` are not
        truncated; the padding is a minimum, not a maximum.
    """
    return "{0}_{1:0{2}d}".format(prefix, number, ID_WIDTH)


def assign_sequential_ids(entities: Iterable, prefix: str) -> None:
    """
    Number a freshly parsed list of entities positionally, in place.

    Used by the Parser, where the source order is the only order that exists
    and every entity is new.
    """
    for index, entity in enumerate(entities, start=1):
        entity.id = format_id(prefix, index)


def highest_number(prefix: str, existing: Iterable[str]) -> int:
    """
    Return the largest numeric suffix among ``existing`` IDs for ``prefix``.

    IDs belonging to another prefix, and IDs that do not end in a number, are
    ignored rather than treated as an error — an unrecognised ID should not be
    able to block minting. Returns 0 when nothing matches.
    """
    highest = 0
    for entity_id in existing:
        if not entity_id:
            continue
        match = _SUFFIX_PATTERN.match(entity_id)
        if match is None or match.group("prefix") != prefix:
            continue
        highest = max(highest, int(match.group("number")))
    return highest


def mint_id(prefix: str, existing: Iterable[str]) -> str:
    """
    Return a new unique ID for ``prefix``, one above the highest in use.

    Parameters
    ----------
    prefix:
        Entity prefix, e.g. ``"proj"``.
    existing:
        Every ID already in use for this entity type. May include IDs from
        other prefixes and malformed IDs; both are ignored.

    Returns
    -------
    str
        A new ID, e.g. ``"proj_003"``.

    Notes
    -----
    The new number is ``max + 1``, deliberately not ``count + 1``. When a plan
    removes ``proj_001`` and generates a replacement, counting the survivors
    would mint ``proj_002`` — which the surviving project already owns.
    """
    return format_id(prefix, highest_number(prefix, existing) + 1)


def mint_ids(prefix: str, existing: Iterable[str], count: int) -> List[str]:
    """
    Return ``count`` new unique IDs for ``prefix``, in ascending order.

    Equivalent to calling :func:`mint_id` repeatedly while feeding each result
    back into ``existing``.
    """
    start = highest_number(prefix, existing) + 1
    return [format_id(prefix, start + offset) for offset in range(count)]
