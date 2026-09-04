"""
Joining what the Planner intended to what the pipeline actually produced.

Pure functions over already-validated models: nothing here reads a file, calls
a model, or mutates its arguments.

**Why this module exists.** A ``ResumePlan`` is a statement of *intent*. The
Generator then declines some of it, for reasons documented in
``PROJECT_KNOWLEDGE`` §10b: a ``REMOVE`` is cancelled unless a ``GENERATE``
funded it, a lopsided skill trade is cancelled, an emptied category is dropped.
The Revision Engine then removes further content to reach one page. A report
that read the plan at face value would state removals that never happened and
miss removals nobody planned.

The join is by **entity-id set membership** across the source, generated and
final resumes, plus the ``EntitySource`` the Generator stamped. Both are
recorded facts. The Reporter decides nothing: it never judges whether a change
was correct, never infers a lineage value, and never pairs a source bullet to a
rewritten one, because no such pairing exists.
"""

from typing import Dict, List, Optional, Sequence

from src.parser.models import (
    Education,
    EntitySource,
    Experience,
    Project,
    Resume,
    SkillCategory,
)
from src.planner.models import (
    ExperiencePlan,
    PlanAction,
    ProjectPlan,
    ResumePlan,
    SectionPriority,
    SkillCategoryPlan,
)
from src.quality.models import ResumeSection
from src.revision.models import RevisionAction, RevisionResult, RevisionStep

from .models import EffectiveAction, EntityChange, PlanEntry

#: Separator in a ``BulletRef.bullet_id`` ("exp_001:bullet_3").
_BULLET_ID_SEPARATOR = ":"


# ----------------------------------------------------------------------
# Small shared helpers
# ----------------------------------------------------------------------


def added(before: Sequence[str], after: Sequence[str]) -> List[str]:
    """Return items present only in ``after``, in ``after``'s own order."""
    return [item for item in after if item not in before]


def removed(before: Sequence[str], after: Sequence[str]) -> List[str]:
    """Return items present only in ``before``, in ``before``'s own order."""
    return [item for item in before if item not in after]


def priority_name(priority: SectionPriority) -> str:
    """
    Return a plan priority as its name.

    ``SectionPriority`` is an ``IntEnum`` and serialises as ``3`` rather than
    ``"MEDIUM"``, which is unreadable in a report. Documented in
    ``PROJECT_KNOWLEDGE`` §10.
    """
    return SectionPriority(priority).name


def experience_label(experience: Experience) -> str:
    """Return a human name for an experience."""
    return "{0} - {1}".format(experience.company, experience.role)


def education_label(education: Education) -> str:
    """Return a human name for an education entry."""
    return "{0} - {1}".format(education.institution, education.degree)


def _by_id(entities: Sequence[object]) -> Dict[str, object]:
    """Index entities by their runtime id."""
    return {getattr(e, "id"): e for e in entities}


def _effective_action(
    planned: Optional[PlanAction], in_generated: bool, in_final: bool
) -> EffectiveAction:
    """
    Decide what happened to a source entity from presence, not from prose.

    Presence in the generated resume answers "did the Generator honour the
    plan"; presence in the final one answers "did the Revision Engine keep it".
    """
    if in_final:
        if planned is PlanAction.REMOVE:
            return EffectiveAction.REMOVAL_CANCELLED
        if planned is PlanAction.REWRITE:
            return EffectiveAction.REWRITTEN
        return EffectiveAction.KEPT
    if in_generated:
        return EffectiveAction.TRIMMED_FOR_PAGE_FIT
    if planned is PlanAction.REMOVE:
        return EffectiveAction.REMOVED
    return EffectiveAction.DROPPED_UNPLANNED


def _cancellation_note(action: EffectiveAction) -> Optional[str]:
    """Return the standing explanation for a plan/outcome disagreement."""
    if action is EffectiveAction.REMOVAL_CANCELLED:
        return (
            "planned for removal and still present: the Generator cancels a "
            "removal no GENERATE funded"
        )
    if action is EffectiveAction.DROPPED_UNPLANNED:
        return "absent although no plan entry asked for its removal"
    if action is EffectiveAction.TRIMMED_FOR_PAGE_FIT:
        return "removed by the Revision Engine to reach one page"
    return None


# ----------------------------------------------------------------------
# Plan projection
# ----------------------------------------------------------------------


def plan_entries(plan: ResumePlan, source: Resume) -> List[PlanEntry]:
    """
    Project a ``ResumePlan`` into report-shaped entries, in section order.

    Labels come from the source resume, because the plan addresses entities by
    runtime id only and an id alone does not say which project it names.
    """
    entries = [
        PlanEntry(
            section=ResumeSection.SUMMARY,
            label="Summary",
            action=plan.summary_plan.action,
            priority=priority_name(plan.summary_plan.priority),
            reasoning=plan.summary_plan.reasoning,
            keywords_to_include=list(plan.summary_plan.keywords_to_include),
        )
    ]
    skills = _by_id(source.skills)
    for skill_plan in plan.skills_plans:
        entries.append(_skill_plan_entry(skill_plan, skills))
    experiences = _by_id(source.experiences)
    for experience_plan in plan.experience_plans:
        entries.append(_experience_plan_entry(experience_plan, experiences))
    projects = _by_id(source.projects)
    for project_plan in plan.project_plans:
        entries.append(_project_plan_entry(project_plan, projects))
    return entries


def _skill_plan_entry(
    plan: SkillCategoryPlan, source_by_id: Dict[str, object]
) -> PlanEntry:
    """Return the report entry for one skill-category plan."""
    existing = source_by_id.get(plan.category_id or "")
    label = plan.new_category_name or (
        existing.category if existing is not None else "new skill category"
    )
    return PlanEntry(
        section=ResumeSection.SKILLS,
        entity_id=plan.category_id,
        label=label,
        action=plan.action,
        priority=priority_name(plan.priority),
        reasoning=plan.reasoning,
        new_category_name=plan.new_category_name,
        skills_to_add=list(plan.skills_to_add),
        skills_to_remove=list(plan.skills_to_remove),
    )


def _experience_plan_entry(
    plan: ExperiencePlan, source_by_id: Dict[str, object]
) -> PlanEntry:
    """Return the report entry for one experience plan."""
    existing = source_by_id.get(plan.experience_id)
    return PlanEntry(
        section=ResumeSection.EXPERIENCE,
        entity_id=plan.experience_id,
        label=experience_label(existing) if existing is not None else plan.experience_id,
        action=plan.action,
        priority=priority_name(plan.priority),
        reasoning=plan.reasoning,
        rewrite_strategy=plan.rewrite_strategy,
        keywords_to_include=list(plan.keywords_to_include),
        themes_to_emphasize=list(plan.themes_to_emphasize),
    )


def _project_plan_entry(
    plan: ProjectPlan, source_by_id: Dict[str, object]
) -> PlanEntry:
    """Return the report entry for one project plan."""
    existing = source_by_id.get(plan.project_id or "")
    return PlanEntry(
        section=ResumeSection.PROJECTS,
        entity_id=plan.project_id,
        label=existing.name if existing is not None else "generated project",
        action=plan.action,
        priority=priority_name(plan.priority),
        reasoning=plan.reasoning,
        rewrite_strategy=plan.rewrite_strategy,
        generation_brief=plan.generation_brief,
        keywords_to_include=list(plan.keywords_to_include),
        themes_to_emphasize=list(plan.themes_to_emphasize),
    )


# ----------------------------------------------------------------------
# Revision notes
# ----------------------------------------------------------------------


def _entity_of(bullet_id: str) -> str:
    """Return the entity id a ``BulletRef`` id belongs to."""
    return bullet_id.split(_BULLET_ID_SEPARATOR)[0]


def _note_for(step: RevisionStep, entity_id: str) -> Optional[str]:
    """
    Render one trail step as a note, or ``None`` if it is not this entity's.

    The wording comes from the step's own ``action`` and ``detail``; the
    Reporter adds no interpretation.
    """
    if step.action is RevisionAction.COMPRESS_BULLETS:
        mine = [b for b in step.bullet_ids if _entity_of(b) == entity_id]
        if not mine:
            return None
        return "Compressed {0} bullet(s) to satisfy page-fit constraints.".format(
            len(mine)
        )
    if step.entity_id != entity_id:
        return None
    if step.action is RevisionAction.REMOVE_BULLET:
        return "Removed a bullet during deterministic trimming: {0}".format(
            step.detail or "(text not recorded)"
        )
    if step.action is RevisionAction.REMOVE_PROJECT:
        return "Removed the project during deterministic trimming."
    if step.action is RevisionAction.REMOVE_SKILLS:
        return "Removed trailing skills during deterministic trimming."
    if step.action is RevisionAction.REMOVE_SKILL_CATEGORY:
        return "Removed the skill category, emptied by deterministic trimming."
    return step.detail


def revision_notes(revision: Optional[RevisionResult], entity_id: Optional[str]) -> List[str]:
    """Return every trail note that belongs to one entity, in trail order."""
    if revision is None or entity_id is None:
        return []
    notes = []  # type: List[str]
    for step in revision.trail:
        note = _note_for(step, entity_id)
        if note is not None:
            notes.append(note)
    return notes


# ----------------------------------------------------------------------
# Per-section reconciliation
# ----------------------------------------------------------------------


def summary_change(source: Resume, final: Resume, plan: ResumePlan) -> EntityChange:
    """
    Reconcile the summary, which has neither an id nor an ``EntitySource``.

    Its only lineage signal is the plan's action, so a rewrite that returned
    the source text verbatim would still read REWRITTEN. String equality is
    checked and noted -- that is a comparison, not a judgement about quality.
    """
    action = plan.summary_plan.action
    effective = (
        EffectiveAction.REWRITTEN
        if action is PlanAction.REWRITE
        else EffectiveAction.KEPT
    )
    note = None
    if action is PlanAction.REWRITE and source.summary == final.summary:
        note = "planned REWRITE returned the source text unchanged"
    return EntityChange(
        section=ResumeSection.SUMMARY,
        label="Summary",
        planned_action=action,
        planned_priority=priority_name(plan.summary_plan.priority),
        effective_action=effective,
        reconciliation_note=note,
        bullets_before=[source.summary],
        bullets_after=[final.summary],
    )


def _skill_label(source_category: SkillCategory, final: Optional[SkillCategory]) -> str:
    """Return a label that shows a rename when the plan performed one."""
    if final is None or final.category == source_category.category:
        return source_category.category
    return "{0} (renamed from '{1}')".format(final.category, source_category.category)


def skill_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    plan: ResumePlan,
    revision: Optional[RevisionResult],
) -> List[EntityChange]:
    """Reconcile every skill category, source-order first, then new ones."""
    plans = {p.category_id: p for p in plan.skills_plans if p.category_id}
    generated_ids = _by_id(generated.skills)
    final_by_id = _by_id(final.skills)
    changes = []  # type: List[EntityChange]
    for category in source.skills:
        entry = plans.get(category.id)
        effective = _effective_action(
            entry.action if entry is not None else None,
            category.id in generated_ids,
            category.id in final_by_id,
        )
        surviving = final_by_id.get(category.id)
        after = list(surviving.skills) if surviving is not None else []
        changes.append(
            EntityChange(
                section=ResumeSection.SKILLS,
                entity_id=category.id,
                label=_skill_label(category, surviving),
                source=(surviving or category).source,
                planned_action=entry.action if entry is not None else None,
                planned_priority=(
                    priority_name(entry.priority) if entry is not None else None
                ),
                effective_action=effective,
                reconciliation_note=_cancellation_note(effective),
                skills_before=list(category.skills),
                skills_after=after,
                skills_added=added(category.skills, after),
                skills_removed=removed(category.skills, after),
                revision_notes=revision_notes(revision, category.id),
            )
        )
    changes.extend(_new_skill_changes(source, generated, final, revision))
    return changes


def _new_skill_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    revision: Optional[RevisionResult],
) -> List[EntityChange]:
    """Report categories the Generator created, identified by their lineage."""
    source_ids = _by_id(source.skills)
    final_by_id = _by_id(final.skills)
    changes = []  # type: List[EntityChange]
    for category in generated.skills:
        if category.id in source_ids:
            continue
        surviving = final_by_id.get(category.id)
        after = list(surviving.skills) if surviving is not None else []
        effective = (
            EffectiveAction.GENERATED
            if surviving is not None
            else EffectiveAction.TRIMMED_FOR_PAGE_FIT
        )
        changes.append(
            EntityChange(
                section=ResumeSection.SKILLS,
                entity_id=category.id,
                label=(surviving or category).category,
                source=(surviving or category).source,
                effective_action=effective,
                reconciliation_note=_cancellation_note(effective),
                skills_after=after,
                skills_added=after,
                revision_notes=revision_notes(revision, category.id),
            )
        )
    return changes


def experience_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    plan: ResumePlan,
    revision: Optional[RevisionResult],
) -> List[EntityChange]:
    """
    Reconcile experiences.

    An experience can only ever be KEEP or REWRITE -- the plan model forbids
    adding, removing or reordering one, and the Validator requires exactly two
    -- so the presence checks here are a backstop rather than a live path.
    """
    plans = {p.experience_id: p for p in plan.experience_plans}
    generated_ids = _by_id(generated.experiences)
    final_by_id = _by_id(final.experiences)
    changes = []  # type: List[EntityChange]
    for experience in source.experiences:
        entry = plans.get(experience.id)
        surviving = final_by_id.get(experience.id)
        effective = _effective_action(
            entry.action if entry is not None else None,
            experience.id in generated_ids,
            experience.id in final_by_id,
        )
        changes.append(
            _entity_change(
                section=ResumeSection.EXPERIENCE,
                before=experience,
                after=surviving,
                label=experience_label(surviving or experience),
                planned_action=entry.action if entry is not None else None,
                planned_priority=(
                    priority_name(entry.priority) if entry is not None else None
                ),
                effective=effective,
                revision=revision,
            )
        )
    return changes


def project_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    plan: ResumePlan,
    revision: Optional[RevisionResult],
) -> List[EntityChange]:
    """Reconcile every project, source-order first, then generated ones."""
    plans = {p.project_id: p for p in plan.project_plans if p.project_id}
    generated_ids = _by_id(generated.projects)
    final_by_id = _by_id(final.projects)
    changes = []  # type: List[EntityChange]
    for project in source.projects:
        entry = plans.get(project.id)
        effective = _effective_action(
            entry.action if entry is not None else None,
            project.id in generated_ids,
            project.id in final_by_id,
        )
        surviving = final_by_id.get(project.id)
        changes.append(
            _entity_change(
                section=ResumeSection.PROJECTS,
                before=project,
                after=surviving,
                label=(surviving or project).name,
                planned_action=entry.action if entry is not None else None,
                planned_priority=(
                    priority_name(entry.priority) if entry is not None else None
                ),
                effective=effective,
                revision=revision,
            )
        )
    changes.extend(_new_project_changes(source, generated, final, revision))
    return changes


def _new_project_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    revision: Optional[RevisionResult],
) -> List[EntityChange]:
    """
    Report projects the Generator created.

    A ``GENERATE`` plan entry carries ``project_id=None``, so it cannot be
    joined to a resulting project from the plan side. The join runs the other
    way, off the ``EntitySource`` the Generator stamped and the id it minted.
    """
    source_ids = _by_id(source.projects)
    final_by_id = _by_id(final.projects)
    changes = []  # type: List[EntityChange]
    for project in generated.projects:
        if project.id in source_ids:
            continue
        surviving = final_by_id.get(project.id)
        effective = (
            EffectiveAction.GENERATED
            if surviving is not None
            else EffectiveAction.TRIMMED_FOR_PAGE_FIT
        )
        changes.append(
            _entity_change(
                section=ResumeSection.PROJECTS,
                before=None,
                after=surviving or project,
                label=(surviving or project).name,
                planned_action=None,
                planned_priority=None,
                effective=effective,
                revision=revision,
            )
        )
    return changes


def education_changes(source: Resume, final: Resume) -> List[EntityChange]:
    """
    Report education, which has no plan and is never revised.

    Included so ``report.json`` describes the whole resume. Every entry comes
    back KEPT, so ``changes.md`` omits the section.
    """
    final_by_id = _by_id(final.education)
    return [
        EntityChange(
            section=ResumeSection.EDUCATION,
            entity_id=entry.id,
            label=education_label(entry),
            source=entry.source,
            effective_action=(
                EffectiveAction.KEPT
                if entry.id in final_by_id
                else EffectiveAction.DROPPED_UNPLANNED
            ),
            reconciliation_note=(
                None
                if entry.id in final_by_id
                else _cancellation_note(EffectiveAction.DROPPED_UNPLANNED)
            ),
        )
        for entry in source.education
    ]


def _entity_change(
    section: ResumeSection,
    before: Optional[object],
    after: Optional[object],
    label: str,
    planned_action: Optional[PlanAction],
    planned_priority: Optional[str],
    effective: EffectiveAction,
    revision: Optional[RevisionResult],
) -> EntityChange:
    """Build the change record for one experience or project."""
    entity_id = getattr(after if after is not None else before, "id")
    before_highlights = list(before.highlights) if before is not None else []
    before_technologies = list(before.technologies) if before is not None else []
    before_domains = list(before.domains) if before is not None else []
    after_highlights = list(after.highlights) if after is not None else []
    after_technologies = list(after.technologies) if after is not None else []
    after_domains = list(after.domains) if after is not None else []
    return EntityChange(
        section=section,
        entity_id=entity_id,
        label=label,
        source=getattr(after if after is not None else before, "source"),
        planned_action=planned_action,
        planned_priority=planned_priority,
        effective_action=effective,
        reconciliation_note=_cancellation_note(effective),
        bullets_before=before_highlights,
        bullets_after=after_highlights,
        technologies_added=added(before_technologies, after_technologies),
        technologies_removed=removed(before_technologies, after_technologies),
        domains_added=added(before_domains, after_domains),
        domains_removed=removed(before_domains, after_domains),
        revision_notes=revision_notes(revision, entity_id),
    )


def attach_soft_failures(
    changes: List[EntityChange], notes: Sequence[str]
) -> List[EntityChange]:
    """
    File each Planner/Generator soft-failure note under the entity it names.

    Matched on the runtime id as a substring, which is safe because those ids
    are unambiguous tokens: ``skill_005`` cannot be confused for anything else
    in a sentence. The prose itself is never parsed, and a note naming no id
    stays where it already is -- in ``report.md``'s soft-failures section.

    This is what turns "planned REWRITE, effective REWRITTEN" into something
    a reader can act on: the *reason* the Generator declined part of the plan.
    """
    for change in changes:
        if change.entity_id is None:
            continue
        change.soft_failure_notes = [
            note for note in notes if change.entity_id in note
        ]
    return changes


def entity_changes(
    source: Resume,
    generated: Resume,
    final: Resume,
    plan: ResumePlan,
    revision: Optional[RevisionResult],
    soft_failures: Sequence[str] = (),
) -> List[EntityChange]:
    """Reconcile every section, in the order ``changes.md`` reports them."""
    changes = [summary_change(source, final, plan)]
    changes.extend(skill_changes(source, generated, final, plan, revision))
    changes.extend(experience_changes(source, generated, final, plan, revision))
    changes.extend(project_changes(source, generated, final, plan, revision))
    changes.extend(education_changes(source, final))
    return attach_soft_failures(changes, soft_failures)
