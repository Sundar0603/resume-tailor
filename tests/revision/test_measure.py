"""
Line estimation and the shortfall arithmetic.

The task doc requires ``shortfall = spill - freeable`` as a testable quantity.
It is tested here as exactly that — a pure function — and the engine tests pin
the more important property: that the *loop* is driven by the recompiled
verdict, not by this arithmetic. Task 016 measured spill going 7 -> 7 -> 0 on
real artifacts, so an estimate can size the work and nothing more.
"""

from src.revision import measure

from .conftest import make_bullet, make_resume


class TestLineEstimation:
    """Calibrated against a real PDF: a rendered line holds 14-15 words."""

    def test_the_character_budget_is_the_measured_one(self):
        assert measure.ONE_LINE_CHAR_BUDGET == 108
        assert measure.ONE_LINE_WORD_BUDGET == 15

    def test_a_short_bullet_is_one_line(self):
        assert measure.estimated_lines("Built a caching layer.") == 1

    def test_an_empty_string_still_occupies_a_line(self):
        assert measure.estimated_lines("") == 1
        assert measure.estimated_lines("   ") == 1

    def test_a_bullet_just_over_the_budget_is_two_lines(self):
        assert measure.estimated_lines("x" * 109) == 2

    def test_a_bullet_at_the_budget_is_one_line(self):
        assert measure.estimated_lines("word " * 15) == 1

    def test_a_long_bullet_is_three_lines(self):
        assert measure.estimated_lines("x" * 220) == 3

    def test_the_word_budget_is_a_floor_not_a_second_opinion(self):
        # Fifteen very long words exceed the character budget, and the
        # character estimate wins. The word rule only ever pulls an estimate
        # down to one line, never up.
        text = " ".join(["supercalifragilistic"] * 15)
        assert len(text.split()) == 15
        assert measure.estimated_lines(text) == 3


class TestCompressionEligibility:
    """One-line bullets are never sent to a model to be made shorter."""

    def test_a_one_line_bullet_is_not_eligible(self):
        assert measure.is_two_line_bullet("Built a Redis cache.") is False

    def test_a_two_line_bullet_is(self):
        assert measure.is_two_line_bullet(make_bullet("Built", 30)) is True


class TestSectionEstimates:
    """Skill categories and projects, for the freeable calculation."""

    def test_an_empty_category_renders_as_nothing(self):
        resume = make_resume(skill_sizes=(3,))
        resume.skills[0].skills = []
        assert measure.skill_category_lines(resume.skills[0]) == 0

    def test_a_short_category_is_one_line(self):
        resume = make_resume(skill_sizes=(3,))
        assert measure.skill_category_lines(resume.skills[0]) == 1

    def test_a_long_category_wraps(self):
        resume = make_resume(skill_sizes=(3,))
        resume.skills[0].skills = ["A reasonably long skill name {0}".format(n) for n in range(8)]
        assert measure.skill_category_lines(resume.skills[0]) >= 2

    def test_a_project_costs_its_bullets_plus_its_chrome(self):
        resume = make_resume(project_bullets=(3,))
        assert measure.project_lines(resume.projects[0]) == 3 + measure.PROJECT_CHROME_LINES


class TestTheWholeResumeEstimate:
    """Coarse, but monotone in content — which is all it is used for."""

    def test_removing_a_bullet_lowers_the_estimate(self):
        big = measure.estimated_resume_lines(make_resume(project_bullets=(4, 4)))
        small = measure.estimated_resume_lines(make_resume(project_bullets=(3, 4)))
        assert small < big

    def test_removing_a_skill_category_lowers_the_estimate(self):
        big = measure.estimated_resume_lines(make_resume(skill_sizes=(4, 4, 4)))
        small = measure.estimated_resume_lines(make_resume(skill_sizes=(4, 4)))
        assert small < big


class TestShortfall:
    """The four cases the task doc names."""

    def test_no_spill_means_no_shortfall(self):
        assert measure.shortfall(0, 9) == 0

    def test_spill_within_freeable_means_no_shortfall(self):
        assert measure.shortfall(5, 9) == 0

    def test_spill_equal_to_freeable_means_no_shortfall(self):
        assert measure.shortfall(9, 9) == 0

    def test_spill_beyond_freeable_is_the_difference(self):
        assert measure.shortfall(13, 9) == 4

    def test_the_task_docs_worked_example(self):
        assert measure.shortfall(13, 9) == 4

    def test_shortfall_never_goes_negative(self):
        assert measure.shortfall(0, 100) == 0


class TestBulletIdentifiers:
    """Ids are 1-based and snapshot-bound, matching proj_002:bullet_3."""

    def test_the_id_is_one_based(self):
        assert measure.bullet_id("proj_002", 2) == "proj_002:bullet_3"

    def test_an_id_round_trips(self):
        assert measure.parse_bullet_id("proj_002:bullet_3") == ["proj_002", "3"]

    def test_a_malformed_id_returns_nothing_rather_than_raising(self):
        assert measure.parse_bullet_id("proj_002") == []
        assert measure.parse_bullet_id("proj_002:bullet_x") == []
        assert measure.parse_bullet_id(":bullet_1") == []
        assert measure.parse_bullet_id("") == []


class TestWordCount:
    """Application code counts words; the model's claim is not evidence."""

    def test_words_are_whitespace_separated(self):
        assert measure.word_count("Built a Redis cache for the API.") == 7

    def test_repeated_whitespace_does_not_inflate_the_count(self):
        assert measure.word_count("Built   a\tcache.\n") == 3
