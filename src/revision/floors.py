"""
Retention floors — the single home for "how far may this be trimmed".

Every floor literal in the Revision Engine lives here. Nothing else in
``src/revision/`` may hard-code a minimum, so changing a policy is a one-file
edit and a reader never has to hunt for the authoritative number.

These floors sit **above** the Validator's own minimums
(``src/validation/validator.py``), which remain the hard backstop: exactly 2
experiences, at least 2 projects, at least 1 skill category, at least 1
education entry, non-empty highlights everywhere. The floors here are a
content-quality policy; the Validator's are a structural contract.

Set by the user on 2026-08-31, superseding the tighter set recorded in
``docs/PROJECT_KNOWLEDGE.md`` §10f (project bullets 3, skill *categories* 5,
skills-per-category 2). Those were measured infeasible — three of six live runs
could not reach one page under them — so they were deliberately relaxed. The
supersession is recorded in §10h.

+------------------------------+-----------+
| unit                         |   minimum |
+==============================+===========+
| projects                     |         2 |
| bullets per project          |         2 |
| individual skills, total     |         5 |
| internship bullets           |         3 |
| full-time experience bullets |         5 |
| work experiences             | exactly 2 |
+------------------------------+-----------+

A project that has reached its bullet floor and is asked to shrink again is
removed whole, rather than being left with one bullet.
"""

from typing import List

from src.parser.models import Experience, Project, Resume, SkillCategory

#: The resume must never fall below this many projects.
MIN_PROJECTS = 2

#: A project is trimmed bullet-by-bullet down to this count, then removed whole.
PROJECT_BULLET_FLOOR = 2

#: Individual skills across every category — five actual skills, not five
#: categories. There is deliberately no per-category floor: a category is
#: dropped when it empties, and a heading with nothing under it renders worse
#: than no heading at all.
MIN_TOTAL_SKILLS = 5

# The Generator sorts skill categories by the Planner's priority, most relevant
# first (``src/generator/generator.py`` — "so the Quality Gate can trim from the
# bottom"). ``SkillCategory`` does not carry the priority itself, so position IS
# the priority here. Protecting the leading categories therefore protects the
# ones the job asked for most loudly: on a database-heavy posting the Databases
# row sorts to the top and becomes untouchable.
PROTECTED_SKILL_CATEGORIES = 1

#: Experiences are never added, removed or reordered. The Validator enforces
#: this too; repeating it here keeps the removal policy self-contained.
REQUIRED_EXPERIENCES = 2

#: Bullet floor for the internship experience.
INTERNSHIP_BULLET_FLOOR = 3

#: Bullet floor for a full-time experience.
FULLTIME_BULLET_FLOOR = 5

#: Independent of every floor above: an entity with no bullets emits an empty
#: ``itemize``, which is a LaTeX *error*, not an empty list. The renderer
#: routes around it for entities that legitimately have none, but a trimmer
#: that empties one has destroyed the document. See PROJECT_KNOWLEDGE §10d.
MIN_BULLETS_PER_ENTITY = 1

#: The ``employment_type`` value that marks an internship. Compared
#: case-insensitively; the parsed literal is ``"Internship"`` in all three
#: canonical resumes and the generator copies the field through verbatim.
INTERNSHIP_EMPLOYMENT_TYPE = "internship"


def is_internship(experience: Experience) -> bool:
    """
    Return whether an experience is an internship.

    Keyed on ``employment_type`` rather than position, so a resume listing its
    jobs in another order still trims the internship first. The field is
    immutable through generation and is deliberately dropped by the LaTeX
    renderer, so it is available at runtime and invisible on the page.
    """
    return experience.employment_type.strip().casefold() == INTERNSHIP_EMPLOYMENT_TYPE


def experience_bullet_floor(experience: Experience) -> int:
    """Return the bullet floor that applies to one experience."""
    if is_internship(experience):
        return INTERNSHIP_BULLET_FLOOR
    return FULLTIME_BULLET_FLOOR


def can_remove_project_bullet(project: Project) -> bool:
    """Return whether one more bullet may be taken from this project."""
    return len(project.highlights) > PROJECT_BULLET_FLOOR


def can_remove_project(resume: Resume) -> bool:
    """Return whether a whole project may be removed from this resume."""
    return len(resume.projects) > MIN_PROJECTS


def can_remove_skill(resume: Resume) -> bool:
    """Return whether one more individual skill may be removed."""
    return removable_skills(resume) > 0


def trimmable_skill_categories(resume: Resume) -> List[SkillCategory]:
    """Return the categories deletion may touch, highest-priority ones excluded."""
    return list(resume.skills[PROTECTED_SKILL_CATEGORIES:])


def removable_skills(resume: Resume) -> int:
    """
    Return how many individual skills may still be removed.

    Bounded twice: by the resume-wide floor, and by how many skills actually
    sit outside the protected leading categories.
    """
    outside = sum(len(c.skills) for c in trimmable_skill_categories(resume))
    return max(0, min(outside, resume.total_skills() - MIN_TOTAL_SKILLS))


def can_remove_experience_bullet(experience: Experience) -> bool:
    """Return whether one more bullet may be taken from this experience."""
    floor = max(experience_bullet_floor(experience), MIN_BULLETS_PER_ENTITY)
    return len(experience.highlights) > floor


def check_invariants(resume: Resume) -> List[str]:
    """
    Return every stated invariant this resume violates.

    Empty means the removal policy can reason about the resume. The engine
    calls this once, up front, and raises rather than trimming a shape it was
    never designed for.

    Two invariants, both stated rather than inferred:

    - Exactly two work experiences. The Validator requires this and the
      removal order assumes it.
    - An internship is always present. Confirmed by the user; no fallback is
      built for its absence, because an untestable branch is worse than a
      documented assumption. Failing loudly beats silently mis-ordering the
      experience trim.
    """
    reasons = []  # type: List[str]

    if len(resume.experiences) != REQUIRED_EXPERIENCES:
        reasons.append(
            "expected exactly {0} work experiences, found {1}".format(
                REQUIRED_EXPERIENCES, len(resume.experiences)
            )
        )

    if not any(is_internship(e) for e in resume.experiences):
        reasons.append(
            "no experience has employment_type 'Internship'; the removal order "
            "trims internship bullets before full-time ones and cannot order "
            "a resume without one"
        )

    return reasons
