"""
ResumeGenerator — the component that writes the tailored resume.

Consumes a source ``Resume``, a ``JobAnalysis`` and a ``ResumePlan``, and
returns a new ``Resume``. It follows the plan rather than deciding for itself
what should change: the Planner already made those decisions.

Three LLM calls, one per prose section — summary, experiences, projects — plus
a fourth section, skills, applied in pure Python because the Planner already
supplies literal category names and skill strings. Splitting the work keeps
each prompt small enough for a local model and stops one bad section from
destroying the rest.

The Generator holds no state between calls. The Revision Engine will call it
repeatedly, and a second call must never inherit anything from the first.
"""

import copy
import json
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from src.analyzer._json_extract import extract_json_object
from src.analyzer.models import JobAnalysis
from src.analyzer.provider import LLMProvider
from src.parser.models import (
    EntitySource,
    Experience,
    Project,
    Resume,
    SkillCategory,
)
from src.validation import ResumeValidator
from src.validation.models import ValidationIssue

from ..entity_ids import PROJECT_PREFIX, SKILL_PREFIX, mint_id
from ..planner.models import (
    PlanAction,
    PlanningMode,
    ProjectPlan,
    ResumePlan,
    SkillCategoryPlan,
)
from .canonical import (
    canonicalize_experiences,
    canonicalize_projects,
    canonicalize_summary,
)
from .constraints import enforce_strict
from .exceptions import (
    GenerationConstraintError,
    GeneratorError,
    GeneratorResponseValidationError,
    InvalidGeneratorJSON,
    InvalidGeneratorResponse,
)
from .models import ExperienceResponse, ProjectResponse, SummaryResponse
from .prompts import (
    build_experiences_prompt,
    build_projects_prompt,
    build_summary_prompt,
)
from .sampling import GENERATOR_TEMPERATURE, generator_options

#: The validator requires at least this many projects to survive.
MIN_PROJECT_COUNT = 2


class ResumeGenerator:
    """
    Transforms a source resume into a tailored resume by following a plan.

    Parameters
    ----------
    provider:
        Any :class:`~src.analyzer.provider.LLMProvider` implementation.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._validator = ResumeValidator()

        #: Validator warnings from the most recent call. Warnings never fail a
        #: generation, but the caller should be able to surface them.
        self.last_warnings: List[ValidationIssue] = []

        #: Soft failures from the most recent call: plan instructions that could
        #: not be carried out but did not justify discarding the generation.
        self.last_discarded: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        *,
        source_resume: Resume,
        job_analysis: JobAnalysis,
        resume_plan: ResumePlan,
        mode: Optional[PlanningMode] = None,
        temperature: float = GENERATOR_TEMPERATURE,
    ) -> Resume:
        """
        Generate a tailored resume.

        Parameters
        ----------
        source_resume:
            The canonical resume. Never mutated.
        job_analysis:
            The structured analysis of the target job.
        resume_plan:
            The plan to follow. Its ``mode`` selects the tailoring rules.
        mode:
            Optional explicit mode. Defaults to the plan's. Passing one that
            disagrees with the plan is an error rather than a silent
            preference, because the two layers enforce different halves of the
            same contract.
        temperature:
            Sampling temperature for the prose calls.

        Returns
        -------
        Resume
            A new resume. Structurally valid, or an exception was raised.

        Raises
        ------
        GeneratorError
            Transport failure, or a mode that disagrees with the plan.
        InvalidGeneratorResponse
            Empty response, or one the section schema rejects.
        InvalidGeneratorJSON
            No parseable JSON in a response.
        GenerationConstraintError
            Strict-mode fabrication, or fewer than two surviving projects.
        GeneratorResponseValidationError
            The assembled resume failed ResumeValidator.
        """
        self.last_warnings = []
        self.last_discarded = []

        resolved = self._resolve_mode(resume_plan, mode)
        working = source_resume.model_copy(deep=True)

        skills = self._apply_skills(working, resume_plan, job_analysis)
        summary = self._generate_summary(
            working, job_analysis, resume_plan, resolved, temperature
        )
        experiences = self._generate_experiences(
            working, job_analysis, resume_plan, resolved, temperature
        )
        projects = self._generate_projects(
            working, job_analysis, resume_plan, resolved, temperature
        )

        generated = Resume(
            metadata=copy.deepcopy(source_resume.metadata),
            contact=copy.deepcopy(source_resume.contact),
            summary=summary,
            skills=skills,
            experiences=experiences,
            projects=projects,
            education=copy.deepcopy(source_resume.education),
        )

        if resolved != PlanningMode.AGGRESSIVE:
            enforce_strict(source_resume, generated)

        self._validate_result(source_resume, generated, resolved)
        return generated

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def _resolve_mode(
        self, resume_plan: ResumePlan, mode: Optional[PlanningMode]
    ) -> PlanningMode:
        """Return the mode to generate under, rejecting a disagreement."""
        if mode is None:
            return resume_plan.mode

        resolved = PlanningMode.parse(mode)
        if resolved != resume_plan.mode:
            raise GeneratorError(
                f"mode {resolved.value} disagrees with the plan's mode "
                f"{resume_plan.mode.value}. The plan was built under its own "
                "mode and cannot be regenerated under another."
            )
        return resolved

    # ------------------------------------------------------------------
    # Skills — pure Python, no LLM call
    # ------------------------------------------------------------------

    def _apply_skills(
        self, resume: Resume, plan: ResumePlan, job_analysis: JobAnalysis
    ) -> List[SkillCategory]:
        """
        Apply the skill plans deterministically.

        No model is involved. A skill is an atomic name, not prose, and the
        Planner already chose the names — a ``GENERATE`` entry arrives carrying
        both ``new_category_name`` and a non-empty ``skills_to_add``.
        """
        by_id = {category.id: category for category in resume.skills}
        keywords = _keyword_order(job_analysis)
        minted: List[str] = [category.id for category in resume.skills]
        result: List[SkillCategory] = []

        for entry in plan.skills_plans:
            if entry.action == PlanAction.REMOVE:
                continue
            if entry.action == PlanAction.GENERATE:
                new_id = mint_id(SKILL_PREFIX, minted)
                minted.append(new_id)
                result.append(
                    SkillCategory(
                        id=new_id,
                        source=EntitySource.GENERATED,
                        category=entry.new_category_name,
                        skills=_order_skills(list(entry.skills_to_add), keywords),
                    )
                )
                continue

            existing = by_id.get(entry.category_id)
            if existing is None:
                # The planner guarantees every id resolves, so this only fires
                # if a caller hand-built a plan against a different resume.
                self.last_discarded.append(
                    f"skill category {entry.category_id} is not in the resume"
                )
                continue

            result.append(self._apply_skill_category(existing, entry, keywords))

        return result

    def _apply_skill_category(
        self,
        existing: SkillCategory,
        entry: SkillCategoryPlan,
        keywords: List[str],
    ) -> SkillCategory:
        """Return one category with the plan's edits applied."""
        if entry.action == PlanAction.KEEP:
            return existing.model_copy(deep=True)

        removals = {skill.casefold() for skill in entry.skills_to_remove}
        kept = [s for s in existing.skills if s.casefold() not in removals]

        present = {skill.casefold() for skill in kept}
        for skill in entry.skills_to_add:
            if skill.casefold() not in present:
                kept.append(skill)
                present.add(skill.casefold())

        return SkillCategory(
            id=existing.id,
            source=existing.source,
            category=entry.new_category_name or existing.category,
            skills=_order_skills(kept, keywords),
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        resume: Resume,
        job_analysis: JobAnalysis,
        plan: ResumePlan,
        mode: PlanningMode,
        temperature: float,
    ) -> str:
        """Rewrite the summary, or return the source summary for KEEP."""
        if plan.summary_plan.action == PlanAction.KEEP:
            return resume.summary

        prompt = build_summary_prompt(resume, job_analysis, plan, mode)
        data = canonicalize_summary(self._call(prompt, temperature))
        response = self._parse_section(SummaryResponse, data, "summary")

        if not response.summary.strip():
            raise InvalidGeneratorResponse(
                "The model returned an empty summary."
            )
        return response.summary.strip()

    # ------------------------------------------------------------------
    # Experiences
    # ------------------------------------------------------------------

    def _generate_experiences(
        self,
        resume: Resume,
        job_analysis: JobAnalysis,
        plan: ResumePlan,
        mode: PlanningMode,
        temperature: float,
    ) -> List[Experience]:
        """
        Rewrite the experiences the plan marks REWRITE, preserving the rest.

        Order and count are taken from the source, never from the response: the
        validator compares experiences positionally, and there must be exactly
        two.
        """
        rewrites = {
            p.experience_id: p
            for p in plan.experience_plans
            if p.action == PlanAction.REWRITE
        }
        if not rewrites:
            return [e.model_copy(deep=True) for e in resume.experiences]

        prompt = build_experiences_prompt(resume, job_analysis, plan, mode)
        data = canonicalize_experiences(self._call(prompt, temperature))
        response = self._parse_section(ExperienceResponse, data, "experiences")

        written = {entry.experience_id: entry for entry in response.experiences}
        self._require_ids(set(written), set(rewrites), "experience")

        result: List[Experience] = []
        for source_experience in resume.experiences:
            entry = written.get(source_experience.id)
            if entry is None:
                result.append(source_experience.model_copy(deep=True))
                continue

            result.append(
                Experience(
                    # Immutable in every mode, re-imposed from the source
                    # rather than trusted from the model.
                    id=source_experience.id,
                    source=source_experience.source,
                    company=source_experience.company,
                    employment_type=source_experience.employment_type,
                    duration=source_experience.duration,
                    location=source_experience.location,
                    # Mutable in aggressive mode only.
                    role=(
                        entry.role.strip() or source_experience.role
                        if mode == PlanningMode.AGGRESSIVE
                        else source_experience.role
                    ),
                    technologies=list(entry.technologies),
                    domains=list(entry.domains),
                    highlights=list(entry.highlights),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def _generate_projects(
        self,
        resume: Resume,
        job_analysis: JobAnalysis,
        plan: ResumePlan,
        mode: PlanningMode,
        temperature: float,
    ) -> List[Project]:
        """Apply the project plans, calling the model only when needed."""
        wanted = [
            p
            for p in plan.project_plans
            if p.action in (PlanAction.REWRITE, PlanAction.GENERATE)
        ]

        written: Dict[str, Any] = {}
        new_entries: List[Any] = []
        if wanted:
            prompt = build_projects_prompt(resume, job_analysis, plan, mode)
            data = canonicalize_projects(self._call(prompt, temperature))
            response = self._parse_section(ProjectResponse, data, "projects")

            for entry in response.projects:
                if entry.project_id is None:
                    new_entries.append(entry)
                else:
                    written[entry.project_id] = entry

            rewrites = {
                p.project_id for p in wanted if p.action == PlanAction.REWRITE
            }
            self._require_ids(set(written), rewrites, "project")

            generate_count = sum(
                1 for p in wanted if p.action == PlanAction.GENERATE
            )
            if len(new_entries) < generate_count:
                raise InvalidGeneratorResponse(
                    f"The plan asked for {generate_count} new project(s) but the "
                    f"model returned {len(new_entries)}."
                )

        result = self._assemble_projects(resume, plan, written, new_entries)

        if len(result) < MIN_PROJECT_COUNT:
            raise GenerationConstraintError(
                f"The plan leaves {len(result)} project(s); a resume must keep at "
                f"least {MIN_PROJECT_COUNT}."
            )
        return result

    def _assemble_projects(
        self,
        resume: Resume,
        plan: ResumePlan,
        written: Dict[str, Any],
        new_entries: List[Any],
    ) -> List[Project]:
        """Build the final project list, minting ids for generated entries."""
        by_id = {project.id: project for project in resume.projects}
        minted: List[str] = [project.id for project in resume.projects]
        pending_new = list(new_entries)
        result: List[Project] = []

        for entry in plan.project_plans:
            if entry.action == PlanAction.REMOVE:
                continue

            if entry.action == PlanAction.GENERATE:
                if not pending_new:
                    break
                content = pending_new.pop(0)
                new_id = mint_id(PROJECT_PREFIX, minted)
                minted.append(new_id)
                result.append(
                    Project(
                        id=new_id,
                        source=EntitySource.GENERATED,
                        name=content.name,
                        type=content.type,
                        # A repository URL cannot be invented.
                        repository=None,
                        technologies=list(content.technologies),
                        domains=list(content.domains),
                        highlights=list(content.highlights),
                    )
                )
                continue

            existing = by_id.get(entry.project_id)
            if existing is None:
                self.last_discarded.append(
                    f"project {entry.project_id} is not in the resume"
                )
                continue

            result.append(self._apply_project(existing, entry, written))

        return result

    def _apply_project(
        self, existing: Project, entry: ProjectPlan, written: Dict[str, Any]
    ) -> Project:
        """Return one existing project with the plan's edits applied."""
        if entry.action == PlanAction.KEEP:
            return existing.model_copy(deep=True)

        content = written.get(entry.project_id)
        if content is None:
            return existing.model_copy(deep=True)

        return Project(
            id=existing.id,
            source=existing.source,
            name=content.name or existing.name,
            type=content.type or existing.type,
            repository=existing.repository,
            technologies=list(content.technologies),
            domains=list(content.domains),
            highlights=list(content.highlights),
        )

    # ------------------------------------------------------------------
    # Transport — mirrors ResumePlanner._invoke_provider
    # ------------------------------------------------------------------

    def _call(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """Invoke the provider and return the parsed JSON object."""
        try:
            response = self._provider.generate(
                prompt, options=generator_options(temperature)
            )
        except GeneratorError:
            raise
        except Exception as exc:
            raise GeneratorError(
                f"LLM provider raised an unexpected error: {exc}"
            ) from exc

        if not response or not response.strip():
            raise InvalidGeneratorResponse(
                "LLM provider returned an empty response."
            )

        try:
            parsed = json.loads(extract_json_object(response.strip()))
        except json.JSONDecodeError as exc:
            raise InvalidGeneratorJSON(
                f"LLM response is not valid JSON: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise InvalidGeneratorJSON(
                "LLM response is valid JSON but not a JSON object."
            )
        return parsed

    def _parse_section(self, model, data: Dict[str, Any], section: str):
        """Validate a canonicalised response against its section schema."""
        try:
            return model(**data)
        except ValidationError as exc:
            raise InvalidGeneratorResponse(
                f"The {section} response does not conform to its schema: {exc}"
            ) from exc
        except TypeError as exc:
            raise InvalidGeneratorResponse(
                f"Unexpected data shape for the {section} response: {exc}"
            ) from exc

    def _require_ids(self, returned: set, expected: set, kind: str) -> None:
        """Raise when the model skipped or invented an entity id."""
        missing = expected - returned
        if missing:
            raise InvalidGeneratorResponse(
                f"The model returned no content for {kind} "
                f"{', '.join(sorted(missing))}."
            )

        unknown = returned - expected
        if unknown:
            raise InvalidGeneratorResponse(
                f"The model returned content for unknown {kind} "
                f"{', '.join(sorted(unknown))}."
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_result(
        self, source: Resume, generated: Resume, mode: PlanningMode
    ) -> None:
        """Run the ResumeValidator, raising on errors and keeping warnings."""
        result = self._validator.validate(
            source_resume=source,
            generated_resume=generated,
            mode=mode,
        )
        self.last_warnings = list(result.warnings)

        if not result.is_valid:
            detail = "; ".join(
                f"{issue.code.value}: {issue.message}" for issue in result.errors
            )
            raise GeneratorResponseValidationError(
                f"The generated resume failed validation: {detail}"
            )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _keyword_order(job_analysis: JobAnalysis) -> List[str]:
    """Return the job's terms, lowercased, in the order they should surface."""
    ordered: List[str] = []
    seen = set()
    for group in (
        job_analysis.required_skills,
        job_analysis.technologies,
        job_analysis.preferred_skills,
        job_analysis.keywords,
    ):
        for term in group:
            key = term.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def _order_skills(skills: List[str], keywords: List[str]) -> List[str]:
    """
    Put skills the job asked for first, keeping source order within each group.

    A recruiter reads the first few entries of a category and stops. This is
    the one editorial judgement the Generator makes about skills, and it is
    deterministic — no model involved.
    """
    priority = {term: index for index, term in enumerate(keywords)}
    matched = [s for s in skills if s.casefold() in priority]
    unmatched = [s for s in skills if s.casefold() not in priority]
    matched.sort(key=lambda s: priority[s.casefold()])
    return matched + unmatched
