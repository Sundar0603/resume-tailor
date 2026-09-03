"""
The deterministic deletion policy.

Every item under "Deterministic Deletion" in the task doc's test plan lives
here. The policy is a pure function of the resume, so none of this needs a
renderer, a compiler, a PDF or a TeX distribution.
"""

import pytest

from src.parser.models import EntitySource
from src.revision import deletion, floors
from src.revision.models import EntityKind, RevisionAction, RevisionReason

from .conftest import make_resume


def _actions(resume):
    """Return the action sequence the policy would take, as plain strings."""
    return [step.action.value for step in deletion.removal_plan(resume)]


def _run_to_exhaustion(resume):
    """Apply every step the policy offers and return the final resume."""
    for step in deletion.removal_plan(resume):
        resume = deletion.apply_removal(resume, step)
    return resume


class TestTheRemovalOrder:
    """Projects, then Skills, then Experience. This order is authoritative."""

    def test_projects_come_before_skills_and_experience(self):
        resume = make_resume(project_bullets=(4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=6)
        first = deletion.next_removal(resume)
        assert first.entity_kind is EntityKind.PROJECT

    def test_skills_come_before_experience(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 4), fulltime_bullets=6)
        first = deletion.next_removal(resume)
        assert first.entity_kind is EntityKind.SKILL_CATEGORY

    def test_experience_is_last(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=6)
        first = deletion.next_removal(resume)
        assert first.entity_kind is EntityKind.EXPERIENCE

    def test_the_whole_sequence_is_projects_then_skills_then_experience(self):
        resume = make_resume(project_bullets=(4, 4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=7)
        kinds = [s.entity_kind for s in deletion.removal_plan(resume)]
        assert kinds == sorted(
            kinds,
            key=lambda k: [EntityKind.PROJECT, EntityKind.SKILL_CATEGORY, EntityKind.EXPERIENCE].index(k),
        )


class TestProjectBulletRemoval:
    """Lowest priority first, and the weakest project is trimmed first."""

    def test_the_last_bullet_of_the_last_project_goes_first(self):
        resume = make_resume(project_bullets=(4, 4))
        step = deletion.next_removal(resume)
        assert step.entity_id == "proj_002"
        assert step.index == 3

    def test_the_removed_bullet_is_the_one_named(self):
        resume = make_resume(project_bullets=(4, 4))
        step = deletion.next_removal(resume)
        removed = resume.projects[1].highlights[3]
        after = deletion.apply_removal(resume, step)
        assert removed not in after.projects[1].highlights
        assert len(after.projects[1].highlights) == 3

    def test_bullets_above_the_removed_one_keep_their_order(self):
        resume = make_resume(project_bullets=(4, 4))
        before = list(resume.projects[1].highlights[:3])
        after = deletion.apply_removal(resume, deletion.next_removal(resume))
        assert after.projects[1].highlights == before


class TestTheProjectBulletFloor:
    """A project shrinks to two bullets, then goes entirely."""

    def test_a_project_is_trimmed_down_to_the_floor(self):
        resume = make_resume(project_bullets=(4, 4), skill_sizes=(2, 2, 1), fulltime_bullets=5)
        final = _run_to_exhaustion(resume)
        assert [len(p.highlights) for p in final.projects] == [2, 2]

    def test_every_project_reaches_the_floor_before_any_is_removed(self):
        # The task doc's wording is global. Trimming per-project instead would
        # delete a whole two-bullet project while a four-bullet project sat
        # untouched — strictly more content lost for the same page saving.
        resume = make_resume(project_bullets=(4, 2, 2))
        plan = deletion.removal_plan(resume)
        first_removal = next(
            i for i, s in enumerate(plan) if s.action is RevisionAction.REMOVE_PROJECT
        )
        trimmed_before = [
            s for s in plan[:first_removal] if s.entity_kind is EntityKind.PROJECT
        ]
        assert any(s.entity_id == "proj_001" for s in trimmed_before)

    def test_a_project_at_the_floor_is_removed_whole(self):
        resume = make_resume(project_bullets=(2, 2, 2))
        step = deletion.next_removal(resume)
        assert step.action is RevisionAction.REMOVE_PROJECT
        assert step.reason is RevisionReason.PROJECT_REACHED_BULLET_FLOOR
        assert step.entity_id == "proj_003"

    def test_removing_a_project_removes_only_that_one(self):
        resume = make_resume(project_bullets=(2, 2, 2))
        after = deletion.apply_removal(resume, deletion.next_removal(resume))
        assert [p.id for p in after.projects] == ["proj_001", "proj_002"]

    def test_a_project_is_never_left_with_one_bullet(self):
        resume = make_resume(project_bullets=(3, 3, 3), skill_sizes=(2, 2, 1), fulltime_bullets=5)
        final = _run_to_exhaustion(resume)
        assert all(len(p.highlights) >= 2 for p in final.projects)


class TestTheMinimumProjectCount:
    """Never below two projects, whatever else is demanded."""

    def test_two_projects_are_never_reduced(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(2, 2, 1), fulltime_bullets=5)
        assert deletion.next_removal(resume) is None

    def test_exhaustion_leaves_exactly_two_projects(self):
        resume = make_resume(project_bullets=(4, 4, 4, 4), skill_sizes=(2, 2, 1), fulltime_bullets=5)
        assert len(_run_to_exhaustion(resume).projects) == 2

    def test_a_generated_project_keeps_its_lineage_through_a_trim(self):
        resume = make_resume(project_bullets=(4, 4))
        resume.projects[1].source = EntitySource.GENERATED
        after = deletion.apply_removal(resume, deletion.next_removal(resume))
        assert after.projects[1].source is EntitySource.GENERATED
        assert after.projects[1].id == "proj_002"


class TestSkillRemoval:
    """Weakest category first, and never one skill at a time."""

    def test_the_last_category_is_reached_first(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 4))
        step = deletion.next_removal(resume)
        assert step.entity_id == "skill_003"

    def test_a_skills_step_is_sized_to_free_a_line(self):
        # A category renders as one wrapping row, so removing a single skill
        # from a long category frees nothing and would waste a recompile.
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 4))
        step = deletion.next_removal(resume)
        assert step.lines_freed >= 1

    def test_an_emptied_category_is_reported_as_such(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 2))
        step = deletion.next_removal(resume)
        assert step.action is RevisionAction.REMOVE_SKILL_CATEGORY
        assert step.reason is RevisionReason.SKILL_CATEGORY_EMPTIED

    def test_an_emptied_category_is_dropped_not_left_empty(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 2))
        after = deletion.apply_removal(resume, deletion.next_removal(resume))
        assert [c.id for c in after.skills] == ["skill_001", "skill_002"]
        assert all(c.skills for c in after.skills)

    def test_trailing_skills_go_first(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(4, 4, 4))
        resume.skills[2].skills = ["A quite long skill name number {0}".format(n) for n in range(6)]
        kept_head = list(resume.skills[2].skills[:2])
        step = deletion.next_removal(resume)
        after = deletion.apply_removal(resume, step)
        assert after.skills[2].skills[:2] == kept_head

    def test_categories_are_never_reordered(self):
        # Trimming may drop a category; it may never alphabetise or shuffle the
        # survivors, so what remains must stay a subsequence of the original.
        resume = make_resume(
            project_bullets=(4, 4), skill_sizes=(5, 5, 5), fulltime_bullets=8
        )
        original = [c.id for c in resume.skills]
        for step in deletion.removal_plan(resume):
            resume = deletion.apply_removal(resume, step)
            survivors = [c.id for c in resume.skills]
            assert survivors == [i for i in original if i in survivors]


class TestTheSkillFloor:
    """Five individual skills, not five categories."""

    def test_a_resume_at_five_skills_offers_no_skill_step(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=5)
        step = deletion.next_removal(resume)
        assert step is None or step.entity_kind is not EntityKind.SKILL_CATEGORY

    def test_exhaustion_never_drops_below_five_skills(self):
        resume = make_resume(project_bullets=(4, 4), skill_sizes=(6, 6, 6), fulltime_bullets=8)
        assert _run_to_exhaustion(resume).total_skills() >= 5

    def test_at_least_one_category_always_survives(self):
        resume = make_resume(project_bullets=(4, 4), skill_sizes=(6, 6, 6), fulltime_bullets=8)
        assert len(_run_to_exhaustion(resume).skills) >= 1


class TestExperienceBulletRemoval:
    """Internship bullets before full-time ones, weakest first inside each."""

    def test_internship_bullets_are_taken_before_full_time_ones(self):
        resume = make_resume(
            project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=8, intern_bullets=5
        )
        step = deletion.next_removal(resume)
        assert step.entity_id == "exp_002"

    def test_full_time_is_reached_once_the_internship_is_at_its_floor(self):
        resume = make_resume(
            project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=8, intern_bullets=3
        )
        step = deletion.next_removal(resume)
        assert step.entity_id == "exp_001"

    def test_the_lowest_priority_bullet_goes_first(self):
        resume = make_resume(
            project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=8, intern_bullets=3
        )
        step = deletion.next_removal(resume)
        assert step.index == 7

    def test_the_intern_first_rule_yields_nothing_on_a_three_bullet_internship(self):
        # Documented, not a defect: the floor is three and today's resumes
        # carry exactly three, so every experience removal lands on the
        # full-time role. PROJECT_KNOWLEDGE 10f flagged the weaker version.
        resume = make_resume(
            project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=8, intern_bullets=3
        )
        plan = deletion.removal_plan(resume)
        assert all(s.entity_id != "exp_002" for s in plan)


class TestExperienceFloors:
    """Five full-time bullets, three internship bullets, exactly two roles."""

    def test_exhaustion_respects_both_experience_floors(self):
        resume = make_resume(
            project_bullets=(4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=9, intern_bullets=6
        )
        final = _run_to_exhaustion(resume)
        assert len(final.experiences[0].highlights) >= 5
        assert len(final.experiences[1].highlights) >= 3

    def test_experiences_are_never_removed(self):
        resume = make_resume(
            project_bullets=(4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=9, intern_bullets=6
        )
        final = _run_to_exhaustion(resume)
        assert [e.id for e in final.experiences] == ["exp_001", "exp_002"]

    def test_experiences_are_never_reordered(self):
        resume = make_resume(fulltime_bullets=9, intern_bullets=6)
        final = _run_to_exhaustion(resume)
        assert [e.company for e in final.experiences] == ["Acme Corp", "Beta Labs"]

    def test_no_entity_is_ever_emptied_of_bullets(self):
        resume = make_resume(
            project_bullets=(4, 4, 4), skill_sizes=(5, 5), fulltime_bullets=9, intern_bullets=6
        )
        final = _run_to_exhaustion(resume)
        assert all(p.highlights for p in final.projects)
        assert all(e.highlights for e in final.experiences)


class TestWhatIsNeverTouched:
    """Summary, education, contact and the immutable experience fields."""

    def test_the_summary_is_never_trimmed(self):
        resume = make_resume(
            project_bullets=(4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=9, intern_bullets=6
        )
        assert _run_to_exhaustion(resume).summary == resume.summary

    def test_education_is_never_modified(self):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=9)
        assert _run_to_exhaustion(resume).education == resume.education

    def test_contact_is_never_modified(self):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=9)
        assert _run_to_exhaustion(resume).contact == resume.contact

    def test_metadata_is_never_modified(self):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=9)
        assert _run_to_exhaustion(resume).metadata == resume.metadata

    def test_immutable_experience_fields_survive(self):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=9, intern_bullets=6)
        final = _run_to_exhaustion(resume)
        for before, after in zip(resume.experiences, final.experiences):
            assert after.company == before.company
            assert after.role == before.role
            assert after.employment_type == before.employment_type
            assert after.duration == before.duration
            assert after.location == before.location


class TestPurity:
    """Deciding and applying are both pure; the input is never mutated."""

    def test_next_removal_does_not_mutate(self):
        resume = make_resume(project_bullets=(4, 4))
        before = resume.model_dump_json()
        deletion.next_removal(resume)
        assert resume.model_dump_json() == before

    def test_apply_removal_does_not_mutate_its_input(self):
        resume = make_resume(project_bullets=(4, 4))
        before = resume.model_dump_json()
        deletion.apply_removal(resume, deletion.next_removal(resume))
        assert resume.model_dump_json() == before

    def test_apply_removal_returns_a_new_object(self):
        resume = make_resume(project_bullets=(4, 4))
        after = deletion.apply_removal(resume, deletion.next_removal(resume))
        assert after is not resume

    def test_removal_plan_does_not_mutate(self):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=9)
        before = resume.model_dump_json()
        deletion.removal_plan(resume)
        assert resume.model_dump_json() == before


class TestFreeableLines:
    """Computed by dry-running the policy, so it cannot disagree with it."""

    def test_a_resume_at_every_floor_can_free_nothing(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(3, 2), fulltime_bullets=5, intern_bullets=3)
        assert deletion.freeable_lines(resume) == 0

    def test_a_larger_resume_can_free_more(self):
        small = make_resume(project_bullets=(3, 3), skill_sizes=(3, 3), fulltime_bullets=6)
        large = make_resume(project_bullets=(5, 5), skill_sizes=(5, 5, 5), fulltime_bullets=9)
        assert deletion.freeable_lines(large) > deletion.freeable_lines(small)

    def test_it_equals_the_sum_of_the_plans_savings(self):
        resume = make_resume(project_bullets=(4, 4), skill_sizes=(4, 4, 4), fulltime_bullets=8)
        plan = deletion.removal_plan(resume)
        assert deletion.freeable_lines(resume) == sum(s.lines_freed for s in plan)


class TestTermination:
    """Every step strictly shrinks the resume, so the loop must end."""

    def test_every_step_reduces_the_content(self):
        resume = make_resume(
            project_bullets=(5, 5, 5), skill_sizes=(6, 6, 6), fulltime_bullets=9, intern_bullets=6
        )
        size = len(resume.model_dump_json())
        for step in deletion.removal_plan(resume):
            resume = deletion.apply_removal(resume, step)
            assert len(resume.model_dump_json()) < size
            size = len(resume.model_dump_json())

    def test_exhaustion_is_reached(self):
        resume = make_resume(
            project_bullets=(6, 6, 6, 6), skill_sizes=(8, 8, 8), fulltime_bullets=10, intern_bullets=8
        )
        assert deletion.next_removal(_run_to_exhaustion(resume)) is None


class TestApplyRejectsNonsense:
    """The apply half refuses a step it cannot honour."""

    def test_an_unknown_entity_id_raises(self):
        resume = make_resume(project_bullets=(4, 4))
        step = deletion.next_removal(resume)
        step.entity_id = "proj_999"
        with pytest.raises(ValueError):
            deletion.apply_removal(resume, step)

    def test_a_compression_action_is_not_a_removal(self):
        resume = make_resume(project_bullets=(4, 4))
        step = deletion.next_removal(resume)
        step.action = RevisionAction.COMPRESS_BULLETS
        with pytest.raises(ValueError):
            deletion.apply_removal(resume, step)


class TestTheHighestPriorityCategoryIsProtected:
    """
    The Generator sorts skill categories by the Planner's priority, most
    relevant first. Position is therefore the priority, and the leading
    categories are the ones the job asked for most loudly — deletion must
    never reach them, however hungry it gets.
    """

    def test_the_first_category_is_never_selected(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(6, 6), fulltime_bullets=5)
        touched = {
            step.entity_id
            for step in deletion.removal_plan(resume)
            if step.entity_kind is EntityKind.SKILL_CATEGORY
        }
        assert resume.skills[0].id not in touched

    def test_the_first_category_survives_a_run_to_exhaustion(self):
        resume = make_resume(project_bullets=(2, 2), skill_sizes=(6, 6, 6), fulltime_bullets=5)
        final = _run_to_exhaustion(resume)
        assert final.skills[0].id == resume.skills[0].id
        assert final.skills[0].skills == resume.skills[0].skills

    def test_a_lone_category_offers_nothing_to_remove(self):
        resume = make_resume(skill_sizes=(12,))
        assert floors.removable_skills(resume) == 0
        assert floors.can_remove_skill(resume) is False

    def test_the_budget_ignores_skills_inside_protected_categories(self):
        # 12 skills, floor 5 => 7 nominally free, but only 3 sit outside
        # the protected leading category.
        resume = make_resume(skill_sizes=(9, 3))
        assert floors.removable_skills(resume) == 3

    def test_the_resume_wide_floor_still_binds(self):
        # 8 skills, floor 5 => 3 free, even though 6 sit outside.
        resume = make_resume(skill_sizes=(2, 6))
        assert floors.removable_skills(resume) == 3
