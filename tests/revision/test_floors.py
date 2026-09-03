"""
The retention floors, and the invariants the removal policy assumes.

These numbers are policy, not implementation detail: they were set by the user
and they supersede the tighter set recorded in PROJECT_KNOWLEDGE §10f. Pinning
them here means a change to them is a visible, deliberate edit rather than a
silent drift.
"""

import pytest

from src.revision import floors
from src.revision.exceptions import RevisionStateError

from .conftest import make_resume


class TestTheFloorValues:
    """The floors themselves, as the user set them on 2026-08-31."""

    def test_the_project_floors(self):
        assert floors.MIN_PROJECTS == 2
        assert floors.PROJECT_BULLET_FLOOR == 2

    def test_five_individual_skills_not_five_categories(self):
        assert floors.MIN_TOTAL_SKILLS == 5

    def test_the_experience_floors(self):
        assert floors.INTERNSHIP_BULLET_FLOOR == 3
        assert floors.FULLTIME_BULLET_FLOOR == 5
        assert floors.REQUIRED_EXPERIENCES == 2

    def test_no_entity_may_be_emptied_of_bullets(self):
        # An empty itemize is a LaTeX error, not an empty list. This floor is
        # independent of every other one.
        assert floors.MIN_BULLETS_PER_ENTITY == 1


class TestInternshipDetection:
    """Keyed on employment_type, never on position."""

    def test_an_internship_is_recognised(self):
        resume = make_resume()
        assert floors.is_internship(resume.experiences[1]) is True

    def test_a_full_time_role_is_not(self):
        resume = make_resume()
        assert floors.is_internship(resume.experiences[0]) is False

    def test_the_comparison_ignores_case_and_padding(self):
        resume = make_resume()
        resume.experiences[0].employment_type = "  INTERNSHIP  "
        assert floors.is_internship(resume.experiences[0]) is True

    def test_the_floor_follows_the_employment_type(self):
        resume = make_resume()
        assert floors.experience_bullet_floor(resume.experiences[0]) == 5
        assert floors.experience_bullet_floor(resume.experiences[1]) == 3

    def test_ordering_survives_the_experiences_being_listed_the_other_way(self):
        resume = make_resume()
        resume.experiences = list(reversed(resume.experiences))
        assert floors.is_internship(resume.experiences[0]) is True
        assert floors.experience_bullet_floor(resume.experiences[0]) == 3


class TestThePredicates:
    """Each floor expressed as a question the policy can ask."""

    def test_a_project_above_the_bullet_floor_may_lose_one(self):
        resume = make_resume(project_bullets=(3, 2))
        assert floors.can_remove_project_bullet(resume.projects[0]) is True
        assert floors.can_remove_project_bullet(resume.projects[1]) is False

    def test_a_resume_at_the_project_minimum_may_not_lose_a_project(self):
        assert floors.can_remove_project(make_resume(project_bullets=(2, 2))) is False
        assert floors.can_remove_project(make_resume(project_bullets=(2, 2, 2))) is True

    def test_skills_are_counted_individually(self):
        resume = make_resume(skill_sizes=(2, 2, 1))
        assert resume.total_skills() == 5
        assert floors.can_remove_skill(resume) is False
        assert floors.removable_skills(resume) == 0

    def test_the_skill_budget_is_the_surplus_above_five(self):
        resume = make_resume(skill_sizes=(4, 4, 4))
        assert floors.removable_skills(resume) == 7

    def test_an_experience_at_its_floor_may_not_lose_a_bullet(self):
        resume = make_resume(fulltime_bullets=5, intern_bullets=3)
        assert floors.can_remove_experience_bullet(resume.experiences[0]) is False
        assert floors.can_remove_experience_bullet(resume.experiences[1]) is False

    def test_an_experience_above_its_floor_may(self):
        resume = make_resume(fulltime_bullets=6, intern_bullets=4)
        assert floors.can_remove_experience_bullet(resume.experiences[0]) is True
        assert floors.can_remove_experience_bullet(resume.experiences[1]) is True


class TestTheStatedInvariants:
    """
    An internship is assumed to exist. That is a user-confirmed invariant, not
    an inference, and no fallback is built for its absence — an untestable
    branch is worse than a documented assumption. It must fail loudly rather
    than silently mis-order the experience trim.
    """

    def test_a_well_formed_resume_violates_nothing(self):
        assert floors.check_invariants(make_resume()) == []

    def test_a_resume_with_no_internship_is_reported(self):
        resume = make_resume()
        resume.experiences[1].employment_type = "Full Time"
        reasons = floors.check_invariants(resume)
        assert len(reasons) == 1
        assert "Internship" in reasons[0]

    def test_the_wrong_number_of_experiences_is_reported(self):
        resume = make_resume()
        resume.experiences = [resume.experiences[1]]
        reasons = floors.check_invariants(resume)
        assert any("exactly 2 work experiences" in r for r in reasons)

    def test_every_violation_is_reported_in_one_call(self):
        resume = make_resume()
        resume.experiences = [resume.experiences[0]]
        assert len(floors.check_invariants(resume)) == 2

    def test_the_error_carries_the_reasons(self):
        error = RevisionStateError("broken", reasons=["a", "b"])
        assert error.reasons == ["a", "b"]

    def test_the_error_is_a_revision_error(self):
        with pytest.raises(Exception) as caught:
            raise RevisionStateError("broken")
        assert isinstance(caught.value, RevisionStateError)
