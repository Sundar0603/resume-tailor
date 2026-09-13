"""
How much of the Knowledge Base a run is allowed to take, and the duplicate guard.

Every constant lives here and nowhere else, following ``src/revision/floors.py``
— a test asserts no other module defines one. They sit **above** the Revision
Engine's retention floors, which sit above the Validator's minimums, so the
three layers nest rather than contradict:

    Validator minimum  <  revision floor  <  what retrieval hands over

Retrieval hands the Planner a generous but finite slate. Handing over
everything would defeat the point twice: the Planner's prompt would carry a
50-bullet resume, and the Revision Engine would spend its whole budget deleting
content that never had a reason to be there.
"""

import itertools
import re
from typing import List, Sequence, Set, Tuple

from src.vocabulary import normalise

#: Highlights kept for a full-time role. The four resumes ship six; the
#: Revision Engine's floor is five.
FULL_TIME_HIGHLIGHTS = 6

#: Highlights kept for an internship. Every resume ships three and the
#: Revision Engine's floor is three, so this is exact rather than generous.
INTERNSHIP_HIGHLIGHTS = 3

#: Projects handed to the Planner. The Validator requires two; a third gives
#: the Planner something to choose between and the Revision Engine something
#: to give up.
MAX_PROJECTS = 3

#: The Validator's hard minimum, restated so selection can refuse a Knowledge
#: Base that cannot produce a valid resume rather than failing three stages
#: later with a less obvious message.
#:
#: ``src/revision/floors.py`` restates the same rule for its own layer. Three
#: copies of one number is a drift hazard, so
#: ``tests/retrieval/test_retrieval_purity.py`` asserts all three agree rather
#: than trusting them to.
MIN_PROJECTS = 2

#: Highlights kept for a project. Matches the Validator's warning ceiling
#: (``_MAX_PROJECT_HIGHLIGHTS``), so a Knowledge Base project rich enough to
#: carry nine canonical bullets does not hand the Planner a resume that warns
#: on sight. Deduplication alone happened to keep today's projects under the
#: ceiling; a budget makes it true by construction rather than by luck.
MAX_PROJECT_HIGHLIGHTS = 6

#: Skill categories handed over. The richest resume carries six.
MAX_SKILL_CATEGORIES = 6

#: Two highlights are the same fact when this fraction of the shorter one's
#: content words appear in the other.
#:
#: **Measured, not chosen.** Over the 296 highlight pairs in the real Knowledge
#: Base the overlap coefficient is bimodal: 280 pairs (95%) fall at or below
#: 0.43 and are genuinely different facts, while 16 sit at 0.60 or above and
#: are on inspection the same fact reworded for a different resume. The nearest
#: values either side of the gap are 10/21 = 0.476 and 3/5 = 0.600, so every
#: threshold in (0.476, 0.600] flags exactly the same 16 pairs. 0.55 is the
#: middle of that plateau, far enough from both edges that floating-point
#: wobble cannot change a verdict.
#:
#: The pair at exactly 0.600 is the one this guard exists for: the backend
#: resume's "rule management platform for creating, validating, versioning, and
#: deploying" and the fullstack resume's "enabling users to create, edit,
#: validate, and manage". Both are canonical, both are kept in the Knowledge
#: Base, and shipping both on one resume would read as padding.
DUPLICATE_THRESHOLD = 0.55

#: A skill category is redundant when this fraction of its skills already
#: appear in the categories chosen ahead of it.
#:
#: **Measured.** Over the 36 category pairs in the real Knowledge Base the
#: distribution is not merely bimodal, it is a gap: three pairs sit at exactly
#: 1.000 and every other pair at 0.200 or below. The three are
#: ``AI and Agentic Systems`` ⊇ ``AI and Automation`` (a strict subset, 4 of 4)
#: and ``Databases`` ([MySQL]) contained in both ``Backend`` and ``Tools``.
#: Any threshold in (0.2, 1.0] flags exactly those three, so 0.9 is chosen to
#: sit well inside the empty band while still requiring near-total containment.
#:
#: This exists because the Knowledge Base is a *merge* of four resumes that
#: each named their own categories. Two of them called overlapping things
#: "AI and Agentic Systems" and "AI and Automation", and a resume printing both
#: headings — one a subset of the other — reads as padding. Dropping the
#: subsumed one loses no fact: every skill in it is already on the page.
SKILL_SUBSUMPTION_THRESHOLD = 0.9

#: Overlap is computed on content words only. Grammatical filler is shared by
#: every English sentence and would compress the whole scale toward 1.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "for", "in", "to", "with", "on",
        "by", "as", "at", "from", "that", "which", "used", "using", "across",
        "into",
    }
)

#: Words this short carry no signal about whether two sentences say the same
#: thing.
_MIN_WORD_LENGTH = 3

_WORD_PATTERN = re.compile(r"[a-z0-9+#.-]+")


def content_words(text: str) -> Set[str]:
    """Return the content words of a sentence, normalised and deduplicated."""
    return {
        word
        for word in _WORD_PATTERN.findall(normalise(text))
        if len(word) >= _MIN_WORD_LENGTH and word not in _STOPWORDS
    }


def overlap(first: str, second: str) -> float:
    """
    Return the overlap coefficient of two sentences, in ``[0, 1]``.

    ``|A ∩ B| / min(|A|, |B|)`` rather than Jaccard. The two are very different
    here: the rewordings this guard targets differ mostly by *added* words, and
    Jaccard punishes that difference twice by inflating the union. The same
    rule-management pair scores 0.41 by Jaccard and 0.60 by overlap, and only
    the second separates it from the genuinely distinct pairs.
    """
    left, right = content_words(first), content_words(second)
    if not left or not right:
        return 0.0
    return len(left & right) / float(min(len(left), len(right)))


def is_near_duplicate(candidate: str, chosen: Sequence[str]) -> bool:
    """Return whether ``candidate`` restates something already chosen."""
    return any(overlap(candidate, existing) >= DUPLICATE_THRESHOLD for existing in chosen)


def highlight_budget(employment_type: str) -> int:
    """
    Return how many highlights an experience of this kind keeps.

    Keyed on ``employment_type`` for the same reason the Revision Engine's trim
    order is (PROJECT_KNOWLEDGE §10f): it is semantic rather than positional,
    so it survives a resume that lists its jobs in another order.
    """
    if "intern" in normalise(employment_type):
        return INTERNSHIP_HIGHLIGHTS
    return FULL_TIME_HIGHLIGHTS


def take_distinct(
    ranked: Sequence[Tuple[str, float]], budget: int
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Take the best ``budget`` items, skipping anything that restates one taken.

    Parameters
    ----------
    ranked
        ``(text, score)`` pairs, already ordered best first.
    budget
        How many to take.

    Returns
    -------
    (taken, rejected)
        ``taken`` is the chosen text in rank order. ``rejected`` pairs each
        skipped text with the text it duplicates, so the Reporter can say why a
        canonical fact did not appear rather than leaving it looking dropped.

    Skipping rather than stopping is what makes "keep every variant" workable:
    a duplicate does not consume the budget, so the next genuinely different
    fact moves up into the slot.
    """
    taken = []  # type: List[str]
    rejected = []  # type: List[Tuple[str, str]]

    for text, _score in ranked:
        if len(taken) >= budget:
            break
        duplicate_of = _first_duplicate(text, taken)
        if duplicate_of is not None:
            rejected.append((text, duplicate_of))
            continue
        taken.append(text)

    return taken, rejected


def _first_duplicate(candidate: str, chosen: Sequence[str]):
    """Return the first chosen text ``candidate`` restates, or None."""
    for existing in chosen:
        if overlap(candidate, existing) >= DUPLICATE_THRESHOLD:
            return existing
    return None


def pairwise_overlaps(texts: Sequence[str]) -> List[Tuple[float, str, str]]:
    """
    Return every pair's overlap, highest first. Used by the threshold tests.

    Exposed so the measurement behind :data:`DUPLICATE_THRESHOLD` can be
    re-run against the real Knowledge Base rather than restated as a comment
    that quietly goes stale.
    """
    scored = [
        (overlap(first, second), first, second)
        for first, second in itertools.combinations(texts, 2)
    ]
    return sorted(scored, key=lambda row: (-row[0], row[1], row[2]))


def is_subsumed(skills: Sequence[str], already_shown: Set[str]) -> bool:
    """
    Return whether every skill here is effectively already on the resume.

    Compared through :func:`src.retrieval.aliases.expand`, so a category
    listing ``Vue`` is recognised as covered by one listing ``Vue.js``.

    An empty category is never "subsumed" — it is empty, which the Generator
    already drops for its own reasons.
    """
    from .aliases import expand

    mine = set()  # type: Set[str]
    for skill in skills:
        mine |= expand(skill)
    if not mine:
        return False
    covered = len(mine & already_shown)
    return covered / float(len(mine)) >= SKILL_SUBSUMPTION_THRESHOLD


def expanded_skills(skills: Sequence[str]) -> Set[str]:
    """Return the alias-expanded form of a category's skills."""
    from .aliases import expand

    expanded = set()  # type: Set[str]
    for skill in skills:
        expanded |= expand(skill)
    return expanded
