"""
ResumeValidator — validates a generated resume against a source resume.

The validator is a pure, stateless component.
It does not read files, load resumes, or mutate either resume.
It simply compares two Resume objects and returns a ValidationResult.
"""

from typing import List

from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Project,
    Resume,
    SkillCategory,
)

from .codes import ValidationCode
from .models import ValidationIssue, ValidationResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED_EXPERIENCE_COUNT = 2
_MIN_PROJECT_COUNT = 2
_MIN_SKILL_CATEGORY_COUNT = 1
_MIN_EDUCATION_COUNT = 1

_SUMMARY_MIN_WORDS = 20
_SUMMARY_MAX_WORDS = 120
_MAX_EXPERIENCE_HIGHLIGHTS = 8
_MAX_PROJECT_HIGHLIGHTS = 6

_VALID_SOURCES = set(EntitySource)


class ResumeValidator:
    """
    Validates a generated resume against the source resume.

    Usage::

        validator = ResumeValidator()
        result = validator.validate(
            source_resume=source_resume,
            generated_resume=generated_resume,
        )
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        *,
        source_resume: Resume,
        generated_resume: Resume,
    ) -> ValidationResult:
        """
        Validate the generated resume against the source resume.

        Parameters
        ----------
        source_resume:
            The canonical resume that was used to start generation.
        generated_resume:
            The resume produced by the Resume Generator.

        Returns
        -------
        ValidationResult
            Contains errors, warnings, and info issues.
            ``is_valid`` is ``True`` only when there are no errors.
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        info: List[ValidationIssue] = []

        errors.extend(self._validate_contact(source_resume, generated_resume))
        errors.extend(self._validate_summary(generated_resume))
        errors.extend(self._validate_skills(generated_resume))
        errors.extend(self._validate_experience(source_resume, generated_resume))
        errors.extend(self._validate_projects(generated_resume))
        errors.extend(self._validate_education(source_resume, generated_resume))
        errors.extend(self._validate_runtime_ids(generated_resume))
        errors.extend(self._validate_entity_sources(generated_resume))

        warnings.extend(self._collect_warnings(generated_resume))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
        )

    # ------------------------------------------------------------------
    # Contact
    # ------------------------------------------------------------------

    def _validate_contact(self, source: Resume, generated: Resume) -> List[ValidationIssue]:
        """Contact is immutable and must exactly match the source resume."""
        issues: List[ValidationIssue] = []

        src = source.contact
        gen = generated.contact

        for field in ("name", "email", "phone", "linkedin", "github"):
            src_val = getattr(src, field, None)
            gen_val = getattr(gen, field, None)

            if not src_val or not gen_val:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MISSING_REQUIRED_FIELD,
                        message=f"Contact field '{field}' is missing.",
                        field=field,
                    )
                )
            elif src_val != gen_val:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MODIFIED_IMMUTABLE_FIELD,
                        message=(
                            f"Contact field '{field}' was modified. "
                            f"Expected '{src_val}', got '{gen_val}'."
                        ),
                        field=field,
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _validate_summary(self, generated: Resume) -> List[ValidationIssue]:
        """Summary must exist and must not be empty."""
        issues: List[ValidationIssue] = []

        if not generated.summary or not generated.summary.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_SUMMARY,
                    message="Summary is missing or empty.",
                    field="summary",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def _validate_skills(self, generated: Resume) -> List[ValidationIssue]:
        """At least one skill category must exist with valid structure."""
        issues: List[ValidationIssue] = []

        if not generated.skills:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_SKILLS,
                    message="Generated resume contains no skill categories.",
                    field="skills",
                )
            )
            return issues

        if len(generated.skills) < _MIN_SKILL_CATEGORY_COUNT:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_SKILL_CATEGORY_COUNT,
                    message=(
                        f"Expected at least {_MIN_SKILL_CATEGORY_COUNT} skill "
                        f"category, found {len(generated.skills)}."
                    ),
                    field="skills",
                )
            )

        seen_ids: List[str] = []
        for sc in generated.skills:
            issues.extend(self._validate_skill_category(sc, seen_ids))

        return issues

    def _validate_skill_category(
        self,
        sc: SkillCategory,
        seen_ids: List[str],
    ) -> List[ValidationIssue]:
        """Validate a single skill category."""
        issues: List[ValidationIssue] = []

        if not sc.id:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_ENTITY_ID,
                    message="Skill category is missing a runtime-generated ID.",
                    field="id",
                )
            )
        elif sc.id in seen_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_ENTITY_ID,
                    entity_id=sc.id,
                    message=f"Duplicate skill category ID '{sc.id}'.",
                    field="id",
                )
            )
        else:
            seen_ids.append(sc.id)

        if not sc.category:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_REQUIRED_FIELD,
                    entity_id=sc.id or None,
                    message="Skill category name (category) is missing.",
                    field="category",
                )
            )

        if sc.skills is None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.EMPTY_SKILLS,
                    entity_id=sc.id or None,
                    message=f"Skill category '{sc.category}' has no skills list.",
                    field="skills",
                )
            )
        else:
            seen_skills: List[str] = []
            for skill in sc.skills:
                if skill in seen_skills:
                    issues.append(
                        ValidationIssue(
                            code=ValidationCode.DUPLICATE_SKILL,
                            entity_id=sc.id or None,
                            message=(
                                f"Duplicate skill '{skill}' in category '{sc.category}'."
                            ),
                            field="skills",
                        )
                    )
                else:
                    seen_skills.append(skill)

        return issues

    # ------------------------------------------------------------------
    # Experience
    # ------------------------------------------------------------------

    def _validate_experience(
        self, source: Resume, generated: Resume
    ) -> List[ValidationIssue]:
        """Exactly two experiences; immutable fields must match source."""
        issues: List[ValidationIssue] = []

        if not generated.experiences:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_EXPERIENCE,
                    message="Generated resume contains no work experiences.",
                    field="experiences",
                )
            )
            return issues

        if len(generated.experiences) != _REQUIRED_EXPERIENCE_COUNT:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_EXPERIENCE_COUNT,
                    message=(
                        f"Expected exactly {_REQUIRED_EXPERIENCE_COUNT} work experiences, "
                        f"found {len(generated.experiences)}."
                    ),
                    field="experiences",
                )
            )

        seen_ids: List[str] = []
        for idx, exp in enumerate(generated.experiences):
            issues.extend(self._validate_single_experience(exp, seen_ids))

            # Immutable field comparison against source (by position)
            if idx < len(source.experiences):
                src_exp = source.experiences[idx]
                issues.extend(
                    self._compare_immutable_experience_fields(src_exp, exp)
                )

        return issues

    def _validate_single_experience(
        self,
        exp: Experience,
        seen_ids: List[str],
    ) -> List[ValidationIssue]:
        """Validate structural integrity of a single experience."""
        issues: List[ValidationIssue] = []

        if not exp.id:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_ENTITY_ID,
                    message="Experience is missing a runtime-generated ID.",
                    field="id",
                )
            )
        elif exp.id in seen_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_ENTITY_ID,
                    entity_id=exp.id,
                    message=f"Duplicate experience ID '{exp.id}'.",
                    field="id",
                )
            )
        else:
            seen_ids.append(exp.id)

        for field in ("company", "role", "duration"):
            if not getattr(exp, field, None):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MISSING_REQUIRED_FIELD,
                        entity_id=exp.id or None,
                        message=f"Experience field '{field}' is missing.",
                        field=field,
                    )
                )

        if exp.technologies is None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.EMPTY_TECHNOLOGIES,
                    entity_id=exp.id or None,
                    message="Experience technologies list is missing.",
                    field="technologies",
                )
            )

        if exp.domains is None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.EMPTY_DOMAINS,
                    entity_id=exp.id or None,
                    message="Experience domains list is missing.",
                    field="domains",
                )
            )

        if not exp.highlights:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.EMPTY_HIGHLIGHTS,
                    entity_id=exp.id or None,
                    message="Experience highlights are empty.",
                    field="highlights",
                )
            )

        return issues

    def _compare_immutable_experience_fields(
        self,
        source: Experience,
        generated: Experience,
    ) -> List[ValidationIssue]:
        """company, role, and duration are immutable."""
        issues: List[ValidationIssue] = []

        for field in ("company", "role", "duration"):
            src_val = getattr(source, field, None)
            gen_val = getattr(generated, field, None)
            if src_val != gen_val:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MODIFIED_IMMUTABLE_FIELD,
                        entity_id=generated.id or None,
                        message=(
                            f"Experience field '{field}' was modified. "
                            f"Expected '{src_val}', got '{gen_val}'."
                        ),
                        field=field,
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def _validate_projects(self, generated: Resume) -> List[ValidationIssue]:
        """At least two projects; each must have required fields."""
        issues: List[ValidationIssue] = []

        if not generated.projects:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_PROJECTS,
                    message="Generated resume contains no projects.",
                    field="projects",
                )
            )
            return issues

        if len(generated.projects) < _MIN_PROJECT_COUNT:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_PROJECT_COUNT,
                    message=(
                        f"Expected at least {_MIN_PROJECT_COUNT} projects, "
                        f"found {len(generated.projects)}."
                    ),
                    field="projects",
                )
            )

        seen_ids: List[str] = []
        for project in generated.projects:
            issues.extend(self._validate_single_project(project, seen_ids))

        return issues

    def _validate_single_project(
        self,
        project: Project,
        seen_ids: List[str],
    ) -> List[ValidationIssue]:
        """Validate structural integrity of a single project."""
        issues: List[ValidationIssue] = []

        if not project.id:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_ENTITY_ID,
                    message="Project is missing a runtime-generated ID.",
                    field="id",
                )
            )
        elif project.id in seen_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_ENTITY_ID,
                    entity_id=project.id,
                    message=f"Duplicate project ID '{project.id}'.",
                    field="id",
                )
            )
        else:
            seen_ids.append(project.id)

        if not project.name:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_REQUIRED_FIELD,
                    entity_id=project.id or None,
                    message="Project name is missing.",
                    field="name",
                )
            )

        if not project.highlights:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.EMPTY_HIGHLIGHTS,
                    entity_id=project.id or None,
                    message=f"Project '{project.name}' highlights are empty.",
                    field="highlights",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Education
    # ------------------------------------------------------------------

    def _validate_education(
        self, source: Resume, generated: Resume
    ) -> List[ValidationIssue]:
        """Education is immutable and must exactly match the source resume."""
        issues: List[ValidationIssue] = []

        if not generated.education:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_EDUCATION,
                    message="Generated resume contains no education entries.",
                    field="education",
                )
            )
            return issues

        if len(generated.education) < _MIN_EDUCATION_COUNT:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_EDUCATION_COUNT,
                    message=(
                        f"Expected at least {_MIN_EDUCATION_COUNT} education entry, "
                        f"found {len(generated.education)}."
                    ),
                    field="education",
                )
            )

        seen_ids: List[str] = []
        for idx, edu in enumerate(generated.education):
            issues.extend(self._validate_single_education(edu, seen_ids))

            # Education is immutable — compare against source by position
            if idx < len(source.education):
                src_edu = source.education[idx]
                issues.extend(
                    self._compare_immutable_education_fields(src_edu, edu)
                )

        return issues

    def _validate_single_education(
        self,
        edu: Education,
        seen_ids: List[str],
    ) -> List[ValidationIssue]:
        """Validate structural integrity of a single education entry."""
        issues: List[ValidationIssue] = []

        if not edu.id:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_ENTITY_ID,
                    message="Education entry is missing a runtime-generated ID.",
                    field="id",
                )
            )
        elif edu.id in seen_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_ENTITY_ID,
                    entity_id=edu.id,
                    message=f"Duplicate education ID '{edu.id}'.",
                    field="id",
                )
            )
        else:
            seen_ids.append(edu.id)

        for field in ("institution", "degree"):
            if not getattr(edu, field, None):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MISSING_REQUIRED_FIELD,
                        entity_id=edu.id or None,
                        message=f"Education field '{field}' is missing.",
                        field=field,
                    )
                )

        return issues

    def _compare_immutable_education_fields(
        self,
        source: Education,
        generated: Education,
    ) -> List[ValidationIssue]:
        """institution, degree, major, and duration are immutable."""
        issues: List[ValidationIssue] = []

        for field in ("institution", "degree", "major", "duration"):
            src_val = getattr(source, field, None)
            gen_val = getattr(generated, field, None)
            if src_val != gen_val:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MODIFIED_IMMUTABLE_FIELD,
                        entity_id=generated.id or None,
                        message=(
                            f"Education field '{field}' was modified. "
                            f"Expected '{src_val}', got '{gen_val}'."
                        ),
                        field=field,
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Runtime IDs
    # ------------------------------------------------------------------

    def _validate_runtime_ids(self, generated: Resume) -> List[ValidationIssue]:
        """
        Every entity must have a non-empty runtime-generated ID.
        IDs must be unique within each entity type.
        """
        issues: List[ValidationIssue] = []

        issues.extend(
            self._check_ids(
                entities=generated.experiences,
                id_getter=lambda e: e.id,
                entity_type="Experience",
            )
        )
        issues.extend(
            self._check_ids(
                entities=generated.projects,
                id_getter=lambda p: p.id,
                entity_type="Project",
            )
        )
        issues.extend(
            self._check_ids(
                entities=generated.education,
                id_getter=lambda e: e.id,
                entity_type="Education",
            )
        )
        issues.extend(
            self._check_ids(
                entities=generated.skills,
                id_getter=lambda s: s.id,
                entity_type="SkillCategory",
            )
        )

        return issues

    def _check_ids(self, entities, id_getter, entity_type: str) -> List[ValidationIssue]:
        """Check that all entities have non-empty, unique IDs."""
        issues: List[ValidationIssue] = []
        seen: List[str] = []

        for entity in entities:
            eid = id_getter(entity)
            if not eid:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MISSING_ENTITY_ID,
                        message=f"{entity_type} is missing a runtime-generated ID.",
                        field="id",
                    )
                )
            elif eid in seen:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.DUPLICATE_ENTITY_ID,
                        entity_id=eid,
                        message=f"Duplicate {entity_type} ID '{eid}'.",
                        field="id",
                    )
                )
            else:
                seen.append(eid)

        return issues

    # ------------------------------------------------------------------
    # Entity Sources
    # ------------------------------------------------------------------

    def _validate_entity_sources(self, generated: Resume) -> List[ValidationIssue]:
        """Every entity must have a valid source value."""
        issues: List[ValidationIssue] = []

        all_entities = [
            *generated.experiences,
            *generated.projects,
            *generated.education,
            *generated.skills,
        ]

        for entity in all_entities:
            source = getattr(entity, "source", None)
            if source is None:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.MISSING_SOURCE,
                        entity_id=getattr(entity, "id", None) or None,
                        message=f"Entity is missing a source value.",
                        field="source",
                    )
                )
            elif source not in _VALID_SOURCES:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_SOURCE,
                        entity_id=getattr(entity, "id", None) or None,
                        message=f"Entity has an invalid source value '{source}'.",
                        field="source",
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def _collect_warnings(self, generated: Resume) -> List[ValidationIssue]:
        """Collect non-fatal warnings. Warnings do not invalidate the resume."""
        warnings: List[ValidationIssue] = []

        warnings.extend(self._warn_summary(generated))
        warnings.extend(self._warn_experience_highlights(generated))
        warnings.extend(self._warn_project_highlights(generated))
        warnings.extend(self._warn_empty_skill_categories(generated))

        return warnings

    def _warn_summary(self, generated: Resume) -> List[ValidationIssue]:
        """Warn if summary word count is outside the recommended range."""
        warnings: List[ValidationIssue] = []

        if not generated.summary:
            return warnings

        word_count = len(generated.summary.split())

        if word_count < _SUMMARY_MIN_WORDS:
            warnings.append(
                ValidationIssue(
                    code=ValidationCode.SUMMARY_TOO_SHORT,
                    message=(
                        f"Summary is too short ({word_count} words). "
                        f"Recommended minimum is {_SUMMARY_MIN_WORDS} words."
                    ),
                    field="summary",
                )
            )
        elif word_count > _SUMMARY_MAX_WORDS:
            warnings.append(
                ValidationIssue(
                    code=ValidationCode.SUMMARY_TOO_LONG,
                    message=(
                        f"Summary is too long ({word_count} words). "
                        f"Recommended maximum is {_SUMMARY_MAX_WORDS} words."
                    ),
                    field="summary",
                )
            )

        return warnings

    def _warn_experience_highlights(self, generated: Resume) -> List[ValidationIssue]:
        """Warn if any experience has more than the recommended highlight count."""
        warnings: List[ValidationIssue] = []

        for exp in generated.experiences:
            if len(exp.highlights) > _MAX_EXPERIENCE_HIGHLIGHTS:
                warnings.append(
                    ValidationIssue(
                        code=ValidationCode.TOO_MANY_EXPERIENCE_HIGHLIGHTS,
                        entity_id=exp.id or None,
                        message=(
                            f"Experience '{exp.company}' has {len(exp.highlights)} highlights. "
                            f"Recommended maximum is {_MAX_EXPERIENCE_HIGHLIGHTS}."
                        ),
                        field="highlights",
                    )
                )

        return warnings

    def _warn_project_highlights(self, generated: Resume) -> List[ValidationIssue]:
        """Warn if any project has more than the recommended highlight count."""
        warnings: List[ValidationIssue] = []

        for project in generated.projects:
            if len(project.highlights) > _MAX_PROJECT_HIGHLIGHTS:
                warnings.append(
                    ValidationIssue(
                        code=ValidationCode.TOO_MANY_PROJECT_HIGHLIGHTS,
                        entity_id=project.id or None,
                        message=(
                            f"Project '{project.name}' has {len(project.highlights)} highlights. "
                            f"Recommended maximum is {_MAX_PROJECT_HIGHLIGHTS}."
                        ),
                        field="highlights",
                    )
                )

        return warnings

    def _warn_empty_skill_categories(self, generated: Resume) -> List[ValidationIssue]:
        """Warn if any skill category has no skills."""
        warnings: List[ValidationIssue] = []

        for sc in generated.skills:
            if not sc.skills:
                warnings.append(
                    ValidationIssue(
                        code=ValidationCode.EMPTY_SKILL_CATEGORY,
                        entity_id=sc.id or None,
                        message=f"Skill category '{sc.category}' has no skills.",
                        field="skills",
                    )
                )

        return warnings
