r"""
The deterministic deletion policy — the whole of it, in one place.

No other component performs deterministic content deletion. The Generator can
only *grow* a resume (it cancels any trade that removes more than it adds), the
Quality Gate judges and never modifies, and the Renderer emits what it is
given. Shrinking to fit one page happens here.

Two pure functions carry the policy:

``next_removal(resume)``
    The single next legal move, or ``None`` when none remains. A pure function
    of the resume — no artifacts, no PDF, no history.
``apply_removal(resume, step)``
    A new resume with that move applied. The input is never mutated.

Splitting decide from apply is what makes the policy testable with nothing
installed, and what makes the engine's loop trivial: ask, apply, recompile,
re-judge.

Removal order, authoritative::

    Projects  ->  Skills  ->  Experience (Internship -> Full-Time)

Within every entity, bullets are already ordered strongest-first by the
Generator's ``_order_highlights``, so "remove the lowest-priority bullet" is
always "remove the last one". That ordering is per-entity, never global — which
is why the order above has to say which *entity* to reach into.

**Projects are trimmed to the floor everywhere before any project is removed.**
The task doc's wording is global: "Projects must be shortened bullet-by-bullet
before the entire project is removed." Doing it per-project instead would
delete a whole two-bullet project while a four-bullet project sat untouched,
which loses strictly more content for the same page saving.

**A skills step is never one skill.** A category renders as a single wrapping
row, so removing one skill from a twelve-skill category frees nothing. Task 016
measured the section at 6-10 lines for 5-8 categories, and trimming every
category to two skills saving only 1-2 lines. With a floor of five *individual*
skills a 21-skill resume offers sixteen nominal removals worth almost no lines,
and taking them one at a time would burn sixteen recompiles before Experience
was ever reached. So each skills step removes exactly as many trailing skills as
it takes to drop that category's rendered line count, or empties it outright.

Termination is structural: every step strictly reduces the resume's content, and
the content is finite. The engine's iteration guard is protection against a bug,
not part of the design.
"""

from typing import List, Optional

from src.parser.models import Resume

from . import floors
from .measure import estimated_lines, project_lines, skill_category_lines
from .models import EntityKind, RemovalStep, RevisionAction, RevisionReason


#: Protection against a policy bug that fails to shrink the resume. Far above
#: any real resume: 20 bullets, 8 categories and a handful of projects put a
#: real exhaustion run well under 60 steps.
_DRY_RUN_GUARD = 500


def next_removal(resume: Resume) -> Optional[RemovalStep]:
    """
    Return the single next legal removal, or ``None`` when none remains.

    Deterministic: the same resume always yields the same step. ``None`` means
    deterministic deletion is exhausted and the engine must either accept the
    resume or move to the compression path.
    """
    for finder in (_next_project_removal, _next_skill_removal, _next_experience_removal):
        step = finder(resume)
        if step is not None:
            return step
    return None


# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------


def _next_project_removal(resume: Resume) -> Optional[RemovalStep]:
    """Trim every project to its bullet floor, then remove whole projects."""
    for index in range(len(resume.projects) - 1, -1, -1):
        project = resume.projects[index]
        if floors.can_remove_project_bullet(project):
            last = len(project.highlights) - 1
            return RemovalStep(
                action=RevisionAction.REMOVE_BULLET,
                reason=RevisionReason.PAGE_OVERFLOW,
                entity_kind=EntityKind.PROJECT,
                entity_id=project.id,
                index=last,
                detail=project.highlights[last],
                lines_freed=estimated_lines(project.highlights[last]),
            )

    if not floors.can_remove_project(resume):
        return None

    index = len(resume.projects) - 1
    project = resume.projects[index]
    return RemovalStep(
        action=RevisionAction.REMOVE_PROJECT,
        reason=RevisionReason.PROJECT_REACHED_BULLET_FLOOR,
        entity_kind=EntityKind.PROJECT,
        entity_id=project.id,
        index=index,
        detail=project.name,
        lines_freed=project_lines(project),
    )


# ----------------------------------------------------------------------
# Skills
# ----------------------------------------------------------------------


def _next_skill_removal(resume: Resume) -> Optional[RemovalStep]:
    """Take trailing skills from the weakest category, in line-sized bites."""
    budget = floors.removable_skills(resume)
    if budget <= 0:
        return None

    # Stops above the protected leading categories — see floors.PROTECTED_SKILL_CATEGORIES.
    for index in range(len(resume.skills) - 1, floors.PROTECTED_SKILL_CATEGORIES - 1, -1):
        category = resume.skills[index]
        if not category.skills:
            continue
        take = _skills_worth_taking(category, budget)
        if take <= 0:
            continue
        removed = category.skills[len(category.skills) - take :]
        empties = take == len(category.skills)
        return RemovalStep(
            action=(
                RevisionAction.REMOVE_SKILL_CATEGORY
                if empties
                else RevisionAction.REMOVE_SKILLS
            ),
            reason=(
                RevisionReason.SKILL_CATEGORY_EMPTIED
                if empties
                else RevisionReason.PAGE_OVERFLOW
            ),
            entity_kind=EntityKind.SKILL_CATEGORY,
            entity_id=category.id,
            index=index,
            skills=list(removed),
            detail=category.category,
            lines_freed=(
                skill_category_lines(category)
                if empties
                else skill_category_lines(category) - _lines_after(category, take)
            ),
        )
    return None


def _skills_worth_taking(category, budget: int) -> int:
    """
    Return how many trailing skills to remove to free at least one line.

    Zero when no affordable number of removals would change the category's
    rendered height — the caller then moves to the next category rather than
    spending a recompile on a change that cannot show up.
    """
    before = skill_category_lines(category)
    limit = min(budget, len(category.skills))
    for take in range(1, limit + 1):
        if take == len(category.skills) or _lines_after(category, take) < before:
            return take
    return 0


def _lines_after(category, take: int) -> int:
    """Return the category's rendered line count with ``take`` trailing skills gone."""
    kept = category.skills[: len(category.skills) - take]
    if not kept:
        return 0
    return skill_category_lines(category.model_copy(update={"skills": kept}))


# ----------------------------------------------------------------------
# Experience
# ----------------------------------------------------------------------


def _next_experience_removal(resume: Resume) -> Optional[RemovalStep]:
    """
    Take the weakest bullet, internships before full-time roles.

    Experiences themselves are never removed and never reordered; only their
    highlights are touched. On today's resumes the internship carries exactly
    three bullets against a floor of three, so this yields nothing there and
    every removal lands on the full-time role. That is the floors working, not
    the ordering failing.
    """
    internships = [e for e in resume.experiences if floors.is_internship(e)]
    full_time = [e for e in resume.experiences if not floors.is_internship(e)]

    for experience in internships + full_time:
        if not floors.can_remove_experience_bullet(experience):
            continue
        last = len(experience.highlights) - 1
        return RemovalStep(
            action=RevisionAction.REMOVE_BULLET,
            reason=RevisionReason.PAGE_OVERFLOW,
            entity_kind=EntityKind.EXPERIENCE,
            entity_id=experience.id,
            index=last,
            detail=experience.highlights[last],
            lines_freed=estimated_lines(experience.highlights[last]),
        )
    return None


# ----------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------


def apply_removal(resume: Resume, step: RemovalStep) -> Resume:
    """
    Return a new resume with ``step`` applied. The input is never mutated.

    Entity ids and :class:`~src.parser.models.EntitySource` values survive
    every removal — a trimmed project is still ``proj_007`` and still
    ``GENERATED``. Only a removed entity loses its id, and it takes it with it.
    """
    revised = resume.model_copy(deep=True)

    if step.action is RevisionAction.REMOVE_PROJECT:
        revised.projects = [
            p for i, p in enumerate(revised.projects) if i != step.index
        ]
        return revised

    if step.action is RevisionAction.REMOVE_SKILL_CATEGORY:
        revised.skills = [c for i, c in enumerate(revised.skills) if i != step.index]
        return revised

    if step.action is RevisionAction.REMOVE_SKILLS:
        category = revised.skills[step.index]
        keep = len(category.skills) - len(step.skills)
        category.skills = category.skills[:keep]
        return revised

    if step.action is RevisionAction.REMOVE_BULLET:
        owner = _bullet_owner(revised, step)
        owner.highlights = [
            h for i, h in enumerate(owner.highlights) if i != step.index
        ]
        return revised

    raise ValueError("apply_removal cannot apply {0}".format(step.action.value))


def _bullet_owner(resume: Resume, step: RemovalStep):
    """Return the project or experience a REMOVE_BULLET step addresses."""
    pool = (
        resume.projects
        if step.entity_kind is EntityKind.PROJECT
        else resume.experiences
    )
    for entity in pool:
        if entity.id == step.entity_id:
            return entity
    raise ValueError("no {0} with id {1}".format(step.entity_kind.value, step.entity_id))


def freeable_lines(resume: Resume) -> int:
    """
    Return the rendered lines deterministic deletion could still recover.

    Computed by dry-running the policy to exhaustion and summing each step's
    estimated saving, so it can never disagree with what the engine would
    actually do — there is one policy, not a policy and a separate model of it.

    An estimate, like everything in :mod:`src.revision.measure`. It decides
    whether the compression path is worth entering, never whether the resume
    fits.
    """
    working = resume
    total = 0
    steps = 0
    while True:
        step = next_removal(working)
        if step is None:
            return total
        total += step.lines_freed
        working = apply_removal(working, step)
        steps += 1
        if steps > _DRY_RUN_GUARD:
            raise RuntimeError("freeable_lines did not terminate; deletion policy is not shrinking")


def removal_plan(resume: Resume) -> List[RemovalStep]:
    """
    Return every step the policy would take, in order, without applying them.

    Diagnostic. Used by the replay script and by tests that assert the removal
    order rather than a single step.
    """
    working = resume
    plan = []  # type: List[RemovalStep]
    while True:
        step = next_removal(working)
        if step is None:
            return plan
        plan.append(step)
        working = apply_removal(working, step)
        if len(plan) > _DRY_RUN_GUARD:
            raise RuntimeError("removal_plan did not terminate; deletion policy is not shrinking")
