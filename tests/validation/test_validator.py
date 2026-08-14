"""
Unit tests for ResumeValidator.

Covers both valid and invalid generated resumes as specified in Task 005.
"""

import pytest

from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)
from src.validation import ResumeValidator, ValidationCode, ValidationResult


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _metadata() -> Metadata:
    return Metadata(resume="backend", template="backend", version="1.0")


def _contact() -> Contact:
    return Contact(
        name="Sundar S",
        phone="+91 7397398343",
        email="sundar@example.com",
        linkedin="https://linkedin.com/in/sundar",
        github="https://github.com/sundar",
    )


def _experience(idx: int = 1, **overrides) -> Experience:
    defaults = dict(
        id=f"exp_{idx:03d}",
        source=EntitySource.CANONICAL,
        company=f"Company {idx}",
        role=f"Software Engineer {idx}",
        employment_type="Full Time",
        duration=f"Jan 202{idx} - Present",
        technologies=["Python", "Django"],
        domains=["Backend"],
        highlights=["Built something great.", "Improved performance by 30%."],
    )
    defaults.update(overrides)
    return Experience(**defaults)


def _project(idx: int = 1, source: EntitySource = EntitySource.CANONICAL, **overrides) -> Project:
    defaults = dict(
        id=f"proj_{idx:03d}",
        source=source,
        name=f"Project {idx}",
        type="Personal",
        technologies=["Python"],
        highlights=["Did something cool."],
    )
    defaults.update(overrides)
    return Project(**defaults)


def _skill_category(idx: int = 1, source: EntitySource = EntitySource.CANONICAL, **overrides) -> SkillCategory:
    defaults = dict(
        id=f"skill_{idx:03d}",
        source=source,
        category=f"Category {idx}",
        skills=["Python", "Java"],
    )
    defaults.update(overrides)
    return SkillCategory(**defaults)


def _education(idx: int = 1, **overrides) -> Education:
    defaults = dict(
        id=f"edu_{idx:03d}",
        source=EntitySource.CANONICAL,
        institution="MIT",
        degree="B.Tech",
        major="Computer Science",
        duration="2018 - 2022",
    )
    defaults.update(overrides)
    return Education(**defaults)


def _valid_source_resume() -> Resume:
    """A canonical source resume with two experiences and one education."""
    return Resume(
        metadata=_metadata(),
        contact=_contact(),
        summary="A seasoned backend engineer with expertise in distributed systems and cloud infrastructure.",
        skills=[_skill_category(1), _skill_category(2)],
        experiences=[_experience(1), _experience(2)],
        projects=[_project(1), _project(2)],
        education=[_education(1)],
    )


def _valid_generated_resume(source: Resume) -> Resume:
    """A valid generated resume that mirrors the source."""
    return Resume(
        metadata=source.metadata,
        contact=source.contact,
        summary=source.summary,
        skills=[
            _skill_category(1, source=EntitySource.GENERATED),
            _skill_category(2, source=EntitySource.GENERATED),
        ],
        experiences=[
            _experience(
                1,
                company=source.experiences[0].company,
                role=source.experiences[0].role,
                duration=source.experiences[0].duration,
            ),
            _experience(
                2,
                company=source.experiences[1].company,
                role=source.experiences[1].role,
                duration=source.experiences[1].duration,
            ),
        ],
        projects=[
            _project(1, source=EntitySource.GENERATED),
            _project(2, source=EntitySource.GENERATED),
        ],
        education=[
            _education(
                1,
                institution=source.education[0].institution,
                degree=source.education[0].degree,
                major=source.education[0].major,
                duration=source.education[0].duration,
            )
        ],
    )


@pytest.fixture
def validator() -> ResumeValidator:
    return ResumeValidator()


@pytest.fixture
def source() -> Resume:
    return _valid_source_resume()


@pytest.fixture
def generated(source: Resume) -> Resume:
    return _valid_generated_resume(source)


def _error_codes(result: ValidationResult):
    return [issue.code for issue in result.errors]


def _warning_codes(result: ValidationResult):
    return [issue.code for issue in result.warnings]


# ---------------------------------------------------------------------------
# Valid resume
# ---------------------------------------------------------------------------


class TestValidResume:
    def test_valid_resume_passes(self, validator, source, generated):
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True
        assert result.errors == []

    def test_valid_resume_with_generated_projects(self, validator, source):
        """Generated projects (GENERATED source) must be accepted."""
        gen = _valid_generated_resume(source)
        gen.projects = [
            _project(1, source=EntitySource.CANONICAL),
            _project(2, source=EntitySource.CANONICAL),
            _project(3, source=EntitySource.GENERATED),
            _project(4, source=EntitySource.GENERATED),
            _project(5, source=EntitySource.GENERATED),
        ]
        result = validator.validate(source_resume=source, generated_resume=gen)
        assert result.is_valid is True

    def test_valid_resume_with_generated_skill_categories(self, validator, source):
        """Generated skill categories (GENERATED source) must be accepted."""
        gen = _valid_generated_resume(source)
        gen.skills = [
            _skill_category(1, source=EntitySource.GENERATED, category="Programming Languages"),
            _skill_category(2, source=EntitySource.GENERATED, category="Cloud & DevOps"),
            _skill_category(3, source=EntitySource.GENERATED, category="AI & LLMs"),
        ]
        result = validator.validate(source_resume=source, generated_resume=gen)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Experience validation
# ---------------------------------------------------------------------------


class TestExperienceValidation:
    def test_three_experiences_is_invalid(self, validator, source, generated):
        generated.experiences = [
            _experience(1), _experience(2), _experience(3)
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.INVALID_EXPERIENCE_COUNT in _error_codes(result)

    def test_one_experience_is_invalid(self, validator, source, generated):
        generated.experiences = [_experience(1)]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.INVALID_EXPERIENCE_COUNT in _error_codes(result)

    def test_no_experiences_is_invalid(self, validator, source, generated):
        generated.experiences = []
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_EXPERIENCE in _error_codes(result)

    def test_duplicate_experience_ids_is_invalid(self, validator, source, generated):
        generated.experiences = [
            _experience(1, id="exp_001"),
            _experience(2, id="exp_001"),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_ENTITY_ID in _error_codes(result)

    def test_modified_company_is_invalid(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company="MODIFIED COMPANY",
            role=source.experiences[0].role,
            duration=source.experiences[0].duration,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_modified_role_is_invalid(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company=source.experiences[0].company,
            role="MODIFIED ROLE",
            duration=source.experiences[0].duration,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_modified_duration_is_invalid(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company=source.experiences[0].company,
            role=source.experiences[0].role,
            duration="MODIFIED DURATION",
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_empty_highlights_is_invalid(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company=source.experiences[0].company,
            role=source.experiences[0].role,
            duration=source.experiences[0].duration,
            highlights=[],
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.EMPTY_HIGHLIGHTS in _error_codes(result)

    def test_missing_experience_id_is_invalid(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            id="",
            company=source.experiences[0].company,
            role=source.experiences[0].role,
            duration=source.experiences[0].duration,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_ENTITY_ID in _error_codes(result)


# ---------------------------------------------------------------------------
# Mode-dependent experience immutability
# ---------------------------------------------------------------------------


def _retitled(source: Resume, role: str) -> Experience:
    """Return experience 1 with a new role and every other field from source."""
    src = source.experiences[0]
    return _experience(
        1,
        company=src.company,
        role=role,
        employment_type=src.employment_type,
        duration=src.duration,
    )


class TestRoleMutability:
    """
    ``role`` is immutable in strict mode and mutable in aggressive mode.

    Aggressive tailoring exists so a role can be retitled to match the target
    job — "Software Engineer" becoming "Backend Engineer". Nothing else about
    the experience may move.
    """

    def test_default_mode_is_strict(self, validator, source, generated):
        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_strict_rejects_retitled_role(self, validator, source, generated):
        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="STRICT"
        )
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_aggressive_accepts_retitled_role(self, validator, source, generated):
        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="AGGRESSIVE"
        )
        assert result.is_valid is True

    def test_mode_is_case_insensitive(self, validator, source, generated):
        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="  aggressive  "
        )
        assert result.is_valid is True

    def test_planning_mode_member_is_accepted(self, validator, source, generated):
        from src.planner.models import PlanningMode

        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(
            source_resume=source,
            generated_resume=generated,
            mode=PlanningMode.AGGRESSIVE,
        )
        assert result.is_valid is True

    def test_unknown_mode_falls_back_to_strict(self, validator, source, generated):
        generated.experiences[0] = _retitled(source, "Backend Engineer")
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="NONSENSE"
        )
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_company_still_immutable_in_aggressive(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company="MODIFIED COMPANY",
            role=source.experiences[0].role,
            duration=source.experiences[0].duration,
        )
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="AGGRESSIVE"
        )
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_duration_still_immutable_in_aggressive(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company=source.experiences[0].company,
            role=source.experiences[0].role,
            duration="MODIFIED DURATION",
        )
        result = validator.validate(
            source_resume=source, generated_resume=generated, mode="AGGRESSIVE"
        )
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_employment_type_is_immutable_in_both_modes(
        self, validator, source, generated
    ):
        for mode in ("STRICT", "AGGRESSIVE"):
            generated.experiences[0] = _experience(
                1,
                company=source.experiences[0].company,
                role=source.experiences[0].role,
                duration=source.experiences[0].duration,
                employment_type="Contract",
            )
            result = validator.validate(
                source_resume=source, generated_resume=generated, mode=mode
            )
            assert result.is_valid is False
            assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_location_is_immutable_in_both_modes(self, validator, source, generated):
        source.experiences[0].location = "Chennai"
        for mode in ("STRICT", "AGGRESSIVE"):
            generated.experiences[0] = _experience(
                1,
                company=source.experiences[0].company,
                role=source.experiences[0].role,
                duration=source.experiences[0].duration,
                location="Bengaluru",
            )
            result = validator.validate(
                source_resume=source, generated_resume=generated, mode=mode
            )
            assert result.is_valid is False
            assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)


# ---------------------------------------------------------------------------
# Project validation
# ---------------------------------------------------------------------------


class TestProjectValidation:
    def test_one_project_is_invalid(self, validator, source, generated):
        generated.projects = [_project(1)]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.INVALID_PROJECT_COUNT in _error_codes(result)

    def test_no_projects_is_invalid(self, validator, source, generated):
        generated.projects = []
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_PROJECTS in _error_codes(result)

    def test_duplicate_project_ids_is_invalid(self, validator, source, generated):
        generated.projects = [
            _project(1, id="proj_001"),
            _project(2, id="proj_001"),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_ENTITY_ID in _error_codes(result)

    def test_empty_project_highlights_is_invalid(self, validator, source, generated):
        generated.projects[0] = _project(1, highlights=[])
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.EMPTY_HIGHLIGHTS in _error_codes(result)

    def test_missing_project_id_is_invalid(self, validator, source, generated):
        generated.projects[0] = _project(1, id="")
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_ENTITY_ID in _error_codes(result)

    def test_three_or_more_projects_is_valid(self, validator, source, generated):
        generated.projects = [
            _project(1), _project(2), _project(3), _project(4)
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Skills validation
# ---------------------------------------------------------------------------


class TestSkillsValidation:
    def test_no_skill_categories_is_invalid(self, validator, source, generated):
        generated.skills = []
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_SKILLS in _error_codes(result)

    def test_duplicate_skill_category_ids_is_invalid(self, validator, source, generated):
        generated.skills = [
            _skill_category(1, id="skill_001"),
            _skill_category(2, id="skill_001"),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_ENTITY_ID in _error_codes(result)

    def test_duplicate_skills_within_category_is_invalid(self, validator, source, generated):
        generated.skills = [
            _skill_category(1, skills=["Python", "Python", "Java"]),
            _skill_category(2),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_SKILL in _error_codes(result)

    def test_missing_skill_category_id_is_invalid(self, validator, source, generated):
        generated.skills = [
            _skill_category(1, id=""),
            _skill_category(2),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_ENTITY_ID in _error_codes(result)


# ---------------------------------------------------------------------------
# Education validation
# ---------------------------------------------------------------------------


class TestEducationValidation:
    def test_no_education_is_invalid(self, validator, source, generated):
        generated.education = []
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_EDUCATION in _error_codes(result)

    def test_modified_institution_is_invalid(self, validator, source, generated):
        generated.education[0] = _education(
            1,
            institution="MODIFIED INSTITUTION",
            degree=source.education[0].degree,
            major=source.education[0].major,
            duration=source.education[0].duration,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_modified_degree_is_invalid(self, validator, source, generated):
        generated.education[0] = _education(
            1,
            institution=source.education[0].institution,
            degree="MODIFIED DEGREE",
            major=source.education[0].major,
            duration=source.education[0].duration,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_duplicate_education_ids_is_invalid(self, validator, source, generated):
        generated.education = [
            _education(1, id="edu_001"),
            _education(2, id="edu_001"),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_ENTITY_ID in _error_codes(result)


# ---------------------------------------------------------------------------
# Contact validation
# ---------------------------------------------------------------------------


class TestContactValidation:
    def test_modified_name_is_invalid(self, validator, source, generated):
        generated.contact = Contact(
            name="MODIFIED NAME",
            phone=source.contact.phone,
            email=source.contact.email,
            linkedin=source.contact.linkedin,
            github=source.contact.github,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_modified_email_is_invalid(self, validator, source, generated):
        generated.contact = Contact(
            name=source.contact.name,
            phone=source.contact.phone,
            email="modified@example.com",
            linkedin=source.contact.linkedin,
            github=source.contact.github,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)

    def test_modified_phone_is_invalid(self, validator, source, generated):
        generated.contact = Contact(
            name=source.contact.name,
            phone="+91 0000000000",
            email=source.contact.email,
            linkedin=source.contact.linkedin,
            github=source.contact.github,
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MODIFIED_IMMUTABLE_FIELD in _error_codes(result)


# ---------------------------------------------------------------------------
# Summary validation
# ---------------------------------------------------------------------------


class TestSummaryValidation:
    def test_missing_summary_is_invalid(self, validator, source, generated):
        generated.summary = ""
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_SUMMARY in _error_codes(result)

    def test_whitespace_only_summary_is_invalid(self, validator, source, generated):
        generated.summary = "   "
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_SUMMARY in _error_codes(result)


# ---------------------------------------------------------------------------
# Entity source validation
# ---------------------------------------------------------------------------


class TestEntitySourceValidation:
    def test_valid_canonical_source_passes(self, validator, source, generated):
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True

    def test_valid_generated_source_passes(self, validator, source, generated):
        generated.projects = [
            _project(1, source=EntitySource.GENERATED),
            _project(2, source=EntitySource.GENERATED),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Runtime ID validation
# ---------------------------------------------------------------------------


class TestRuntimeIdValidation:
    def test_all_entities_must_have_ids(self, validator, source, generated):
        """Entities with empty IDs must fail validation."""
        generated.projects[0] = _project(1, id="")
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.MISSING_ENTITY_ID in _error_codes(result)

    def test_duplicate_ids_across_same_type_is_invalid(self, validator, source, generated):
        generated.projects = [
            _project(1, id="proj_001"),
            _project(2, id="proj_001"),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is False
        assert ValidationCode.DUPLICATE_ENTITY_ID in _error_codes(result)


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


class TestWarnings:
    def test_short_summary_produces_warning(self, validator, source, generated):
        generated.summary = "Short summary."
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True  # warnings do not invalidate
        assert ValidationCode.SUMMARY_TOO_SHORT in _warning_codes(result)

    def test_long_summary_produces_warning(self, validator, source, generated):
        generated.summary = " ".join(["word"] * 130)
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True
        assert ValidationCode.SUMMARY_TOO_LONG in _warning_codes(result)

    def test_too_many_experience_highlights_produces_warning(self, validator, source, generated):
        generated.experiences[0] = _experience(
            1,
            company=source.experiences[0].company,
            role=source.experiences[0].role,
            duration=source.experiences[0].duration,
            highlights=[f"Highlight {i}." for i in range(10)],
        )
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True
        assert ValidationCode.TOO_MANY_EXPERIENCE_HIGHLIGHTS in _warning_codes(result)

    def test_too_many_project_highlights_produces_warning(self, validator, source, generated):
        generated.projects[0] = _project(1, highlights=[f"Highlight {i}." for i in range(8)])
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True
        assert ValidationCode.TOO_MANY_PROJECT_HIGHLIGHTS in _warning_codes(result)

    def test_empty_skill_category_produces_warning(self, validator, source, generated):
        generated.skills = [
            _skill_category(1, skills=[]),
            _skill_category(2),
        ]
        result = validator.validate(source_resume=source, generated_resume=generated)
        assert result.is_valid is True
        assert ValidationCode.EMPTY_SKILL_CATEGORY in _warning_codes(result)
