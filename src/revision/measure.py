"""
How much rendered space a piece of text costs, and how far over the page is.

Pure arithmetic. No I/O, no PDF, no LaTeX, no provider — it must stay callable
in a unit test with nothing installed.

**These are estimates, and the engine does not converge on them.** Task 016
drove the trim loop against real artifacts and watched spill go ``7 -> 7 -> 0``:
removing one bullet changed nothing, the next cleared the page, because the
``\\resumeSubHeadingListStart`` blocks move as a unit rather than reflowing line
by line. So an estimate can say *whether it is worth trying* and *roughly how
many bullets to select*, and nothing more. Convergence is decided by rendering,
compiling and re-running the Quality Gate — at roughly half a second per
compile that is affordable, and it is the only honest signal.

The character budget was measured, not chosen. Task 016 read it off a real PDF:
a rendered line in the template's 553.7pt column holds **14-15 words, or
108-114 characters** at 11pt. 108 is the conservative end, so a bullet is
called two lines only when it is comfortably past one.
"""

import math
from typing import List

from src.parser.models import Project, Resume, SkillCategory

#: Characters a single rendered line holds in the template's text column.
#: Measured at 108-114; the low end is used so the estimate errs toward
#: "this really is two lines" rather than toward optimism.
ONE_LINE_CHAR_BUDGET = 108

#: A bullet at or below this many words is one line regardless of the
#: character estimate. The generator already targets 15 words for exactly this
#: reason, and the two signals agree at the boundary — this is a floor on the
#: estimate, not a second opinion.
ONE_LINE_WORD_BUDGET = 15

#: Rendered rows a project costs beyond its bullets: the title line, plus the
#: structural spacing the template puts around a subheading block. Used only
#: when estimating what removing a *whole* project would free.
PROJECT_CHROME_LINES = 2

#: Rendered rows an experience costs beyond its bullets: company/role line and
#: duration/location line. Experiences are never removed, so this exists only
#: for the whole-resume estimate.
EXPERIENCE_CHROME_LINES = 2

#: Rows every resume pays regardless of content: the contact block, the four
#: section headings with their rules, and the education block.
FIXED_CHROME_LINES = 14


def estimated_lines(text: str) -> int:
    """
    Return how many rendered lines a run of body text is expected to occupy.

    Never returns less than one: a bullet that exists occupies a line.

    Parameters
    ----------
    text
        The bullet or line of prose, as it sits on the ``Resume`` object.
        LaTeX escaping expands a handful of characters, which this ignores —
        the escaped specials are rare enough in resume prose that correcting
        for them would add error rather than remove it.
    """
    stripped = text.strip()
    if not stripped:
        return 1
    if len(stripped.split()) <= ONE_LINE_WORD_BUDGET and len(stripped) <= ONE_LINE_CHAR_BUDGET:
        return 1
    return max(1, int(math.ceil(len(stripped) / float(ONE_LINE_CHAR_BUDGET))))


def is_two_line_bullet(text: str) -> bool:
    """
    Return whether a bullet is a candidate for one-line compression.

    Two lines or more. A one-line bullet is never sent to the model merely to
    make it shorter: it would spend a fact for no rendered gain.
    """
    return estimated_lines(text) >= 2


def skill_category_lines(category: SkillCategory) -> int:
    """
    Return how many rendered lines one skill category occupies.

    A category renders as a single ``Category: a, b, c`` row that wraps like
    any other text. An empty category renders as nothing — the generator drops
    those, and so does the trimmer.
    """
    if not category.skills:
        return 0
    return estimated_lines("{0}: {1}".format(category.category, ", ".join(category.skills)))


def project_lines(project: Project) -> int:
    """Return the estimated rendered rows a whole project occupies."""
    bullets = sum(estimated_lines(h) for h in project.highlights)
    return bullets + PROJECT_CHROME_LINES


def estimated_resume_lines(resume: Resume) -> int:
    """
    Return a rough estimate of the resume's total rendered line count.

    Deliberately coarse. It is not used to decide anything — the compiled PDF
    does that — but it is **monotone** in content, which is what a trim loop
    needs to reason about and what makes an offline test of that loop possible
    at all.
    """
    total = FIXED_CHROME_LINES
    total += estimated_lines(resume.summary)
    total += sum(skill_category_lines(c) for c in resume.skills)
    for experience in resume.experiences:
        total += EXPERIENCE_CHROME_LINES
        total += sum(estimated_lines(h) for h in experience.highlights)
    for project in resume.projects:
        total += project_lines(project)
    return total


def shortfall(spill: int, freeable: int) -> int:
    """
    Return the rendered lines that deterministic deletion cannot recover.

    ``shortfall = spill - freeable``, floored at zero.

    A positive shortfall means deletion alone cannot reach one page without
    breaching a retention floor, and is the only condition under which the
    engine is permitted to call the LLM.

    Parameters
    ----------
    spill
        Lines currently on page two and beyond
        (``QualityMetrics.overflow_line_count``).
    freeable
        Lines deletion could still recover legally
        (``src.revision.deletion.freeable_lines``).
    """
    return max(0, spill - freeable)


def word_count(text: str) -> int:
    """Return the word count used for the compression limit."""
    return len(text.split())


def bullet_id(entity_id: str, index: int) -> str:
    """
    Return the stable id for one bullet: ``"{entity_id}:bullet_{n}"``, 1-based.

    Matches the task doc's ``proj_002:bullet_3``. Positional and therefore
    snapshot-bound — a removal renumbers every bullet after it, so an id must
    never be carried across a deletion.
    """
    return "{0}:bullet_{1}".format(entity_id, index + 1)


def parse_bullet_id(value: str) -> List[str]:
    """
    Split a bullet id back into ``[entity_id, index]`` as strings.

    Returns an empty list when the value is not a well-formed bullet id, so a
    malformed id in a model reply is a rejection rather than an exception.
    """
    if ":bullet_" not in value:
        return []
    entity_id, _, tail = value.partition(":bullet_")
    if not entity_id or not tail.isdigit():
        return []
    return [entity_id, tail]
