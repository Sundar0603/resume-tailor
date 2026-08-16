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
from typing import Any, Dict, List, Optional, Set

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
from ..vocabulary import (
    capitalised_runs,
    decapitalise_mid_sentence,
    is_weak_term,
    normalise,
    normalised_set,
)
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
from .constraints import (
    contains_metric,
    enforce_strict,
    job_vocabulary,
    source_vocabulary,
)
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

        # Strict may only reorder and subset the terms the resume already uses.
        # Aggressive additionally allows anything the job asked for — but only
        # that. A term in neither the resume nor the job is invention, not
        # tailoring, and "Jest" reached a generated resume that way.
        vocabulary = source_vocabulary(source_resume)
        if resolved == PlanningMode.AGGRESSIVE:
            vocabulary = vocabulary | job_vocabulary(job_analysis)

        skills = self._apply_skills(working, resume_plan, job_analysis)
        summary = self._generate_summary(
            working, job_analysis, resume_plan, resolved, temperature
        )
        experiences = self._generate_experiences(
            working, job_analysis, resume_plan, resolved, temperature, vocabulary
        )
        projects = self._generate_projects(
            working, job_analysis, resume_plan, resolved, temperature, vocabulary
        )

        # Bullets are the bulk of the page, so they are what the Quality Gate
        # trims — from the bottom of each list. Ordering them here, once, means
        # no path can ship an experience or project whose weakest bullet is not
        # last. Experiences themselves are never reordered (see
        # _generate_experiences); this reorders only *within* each one.
        # The same pass also fixes capitalisation. A model working a job's
        # vocabulary into prose tends to Capitalise it — "rigorous Software
        # Testing and Code Quality assurance" — which reads like a brochure.
        # The prompts forbid it and the model complies inconsistently at a
        # non-zero temperature, so it is corrected rather than requested.
        job_terms = _keyword_order(job_analysis)
        # The candidate's own title-casing is theirs: "Backend Software
        # Engineer" and "Security Operations Center" contain generic words but
        # were written that way in the source.
        cased = _source_capitalisations(source_resume)
        summary = decapitalise_mid_sentence(summary, cased)
        experiences = [
            e.model_copy(
                update={
                    "highlights": [
                        decapitalise_mid_sentence(h, cased)
                        for h in _order_highlights(e.highlights, job_terms)
                    ]
                }
            )
            for e in experiences
        ]
        projects = [
            p.model_copy(
                update={
                    "highlights": [
                        decapitalise_mid_sentence(h, cased)
                        for h in _order_highlights(p.highlights, job_terms)
                    ]
                }
            )
            for p in projects
        ]

        if resolved == PlanningMode.AGGRESSIVE:
            self._report_unquantified(experiences, projects)

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

    def _report_unquantified(
        self, experiences: List[Experience], projects: List[Project]
    ) -> None:
        """
        Note any experience or project that came back without a number.

        Aggressive mode asks for at least one quantified outcome per section,
        because a bullet with a figure in it is the one a reviewer believes.
        This checks whether the model complied.

        Reported, never raised. Whether a number is *believable* cannot be
        judged mechanically — "cut latency 40%" and "cut latency 97%" are
        indistinguishable to a regular expression — so the prompt carries that
        rule and this only counts. Failing a 40-second generation because one
        project lacked a metric would cost far more than it saves.

        Strict mode never reaches here: it forbids introducing any number that
        is not already in the source resume.
        """
        for experience in experiences:
            if not any(contains_metric(h) for h in experience.highlights):
                self.last_discarded.append(
                    f"experience {experience.id} ({experience.company}) has no "
                    "quantified outcome in any bullet"
                )
        for project in projects:
            if not any(contains_metric(h) for h in project.highlights):
                self.last_discarded.append(
                    f"project {project.id} ({project.name!r}) has no quantified "
                    "outcome in any bullet"
                )

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
        ordered: List[Any] = []

        # A removal is only carried out when something is ready to take the
        # slot. Each GENERATE entry funds one REMOVE; removals beyond that are
        # cancelled. A plan that deletes without generating is asking the
        # resume to shrink for nothing.
        removal_budget = sum(
            1 for e in plan.skills_plans if e.action == PlanAction.GENERATE
        )

        for entry in plan.skills_plans:
            if entry.action == PlanAction.REMOVE:
                if removal_budget > 0:
                    removal_budget -= 1
                    continue
                existing = by_id.get(entry.category_id)
                if existing is not None:
                    self.last_discarded.append(
                        f"skill category {existing.id} ({existing.category!r}): "
                        "removal was cancelled — no new category was generated "
                        "to take its place"
                    )
                    ordered.append((entry.priority, existing.model_copy(deep=True)))
                continue
            if entry.action == PlanAction.GENERATE:
                new_id = mint_id(SKILL_PREFIX, minted)
                minted.append(new_id)
                ordered.append(
                    (
                        entry.priority,
                        SkillCategory(
                            id=new_id,
                            source=EntitySource.GENERATED,
                            category=entry.new_category_name,
                            skills=_order_skills(list(entry.skills_to_add), keywords),
                        ),
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

            applied = self._apply_skill_category(existing, entry, keywords)
            if not applied.skills:
                # A heading with nothing under it is worse on a rendered
                # resume than no heading at all. The validator only warns
                # (EMPTY_SKILL_CATEGORY), so it would ship. This happens when a
                # REWRITE removes every existing skill and its additions were
                # dropped upstream as activity phrases.
                self.last_discarded.append(
                    f"skill category {applied.id} ({applied.category!r}) was "
                    "dropped: the plan left it with no skills"
                )
                continue
            ordered.append((entry.priority, applied))

            # A lopsided trade the plan wanted to make in place: more skills
            # out than in. The removals were cancelled above, so the incoming
            # skills would otherwise be clubbed into a category they do not
            # belong to. When the plan supplied a name for them, give them
            # their own category instead.
            split = self._split_off_new_category(entry, applied, minted, keywords)
            if split is not None:
                minted.append(split.id)
                ordered.append((entry.priority, split))

        if not ordered:
            raise GenerationConstraintError(
                "The plan leaves no skill categories; a resume must keep at "
                "least one."
            )

        # Most relevant first, so the Quality Gate can trim from the bottom to
        # meet the one-page constraint. sorted() is stable, so categories of
        # equal priority keep their plan order.
        ordered.sort(key=lambda pair: int(pair[0]))

        # Order the skills *inside* every category here rather than on each
        # path that produces one. KEEP, a cancelled removal and a cancelled
        # lopsided rewrite all return the source category untouched, and each
        # would otherwise ship in source order — leaving the job's own
        # vocabulary buried at the end of the line the recruiter skims.
        return [
            category.model_copy(
                update={"skills": _order_skills(category.skills, keywords)}
            )
            for _, category in ordered
        ]

    def _split_off_new_category(
        self,
        entry: SkillCategoryPlan,
        applied: SkillCategory,
        minted: List[str],
        keywords: List[str],
    ) -> Optional[SkillCategory]:
        """
        Return a new category for skills a cancelled trade left homeless.

        Only when the plan asked to remove more than it offered *and* named
        the incoming group. Without a name the additions were meant to sit
        beside the existing skills, so merging them in place is right and this
        returns None.
        """
        lopsided = len(entry.skills_to_remove) > len(entry.skills_to_add)
        if not (lopsided and entry.skills_to_add and entry.new_category_name):
            return None

        present = {s.casefold() for s in applied.skills}
        incoming = [s for s in entry.skills_to_add if s.casefold() not in present]
        if not incoming:
            return None

        return SkillCategory(
            id=mint_id(SKILL_PREFIX, minted),
            source=EntitySource.GENERATED,
            category=entry.new_category_name,
            skills=_order_skills(incoming, keywords),
        )

    def _apply_skill_category(
        self,
        existing: SkillCategory,
        entry: SkillCategoryPlan,
        keywords: List[str],
    ) -> SkillCategory:
        """
        Return one category with the plan's edits applied.

        A REWRITE with nothing left to add is treated as a KEEP. The plan
        intended a trade — drop these skills, add those — and the additions
        may have been refused upstream as unsupported or as job-description
        prose. Executing only the removal half turns a trade into a deletion,
        which is how five real skills once vanished and nothing took their
        place. The rename is dropped with it: a category renamed "Testing &
        Quality Assurance" while still listing "Distributed Systems" is
        mislabelled, and the rename was only ever there to describe the
        skills that did not arrive.
        """
        if entry.action == PlanAction.KEEP:
            return existing.model_copy(deep=True)

        if len(entry.skills_to_remove) > len(entry.skills_to_add):
            self.last_discarded.append(
                f"skill category {existing.id} ({existing.category!r}): removal "
                f"of {', '.join(repr(s) for s in entry.skills_to_remove)} was "
                f"cancelled — only {len(entry.skills_to_add)} skill(s) were "
                "available to replace them"
            )
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

        rewritten = response.summary.strip()
        self._report_lost_anchors(resume, rewritten)
        return rewritten

    def _report_lost_anchors(self, resume: Resume, summary: str) -> None:
        """
        Note any concrete detail the rewritten summary dropped for nothing.

        The summary is one paragraph, so there is no "move it to the bottom"
        available and no safe way to graft a fact back into prose. What can be
        done is say so: a summary that traded "2 years at Zoho building
        platforms in Java, Spring Boot and Redis" for "Application Software
        Development professional" gave up everything that made it credible and
        gained a job title.

        Reported, never raised. Prose judgement is not a correctness rule, and
        discarding a whole generation over word choice would cost more than it
        saves.
        """
        original = normalise(resume.summary)
        rewritten = normalise(summary)

        # Keyed by the normalised form, reported in the resume's own casing.
        employers = {normalise(e.company): e.company for e in resume.experiences}
        lost = [
            written
            for key, written in employers.items()
            if key and key in original and key not in rewritten
        ]
        if lost:
            self.last_discarded.append(
                "summary: dropped the employer "
                f"{', '.join(sorted(repr(c) for c in lost))}, which the source "
                "summary named"
            )

        source_terms = {
            normalise(t)
            for e in resume.experiences
            for t in e.technologies
        }
        named = {t for t in source_terms if t and t in original}
        kept = {t for t in named if t in rewritten}
        if named and not kept:
            self.last_discarded.append(
                "summary: dropped every technology the source summary named "
                f"({', '.join(sorted(named))})"
            )

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
        vocabulary: Optional[Set[str]] = None,
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
                    technologies=_restrict(
                        entry.technologies,
                        source_experience.technologies,
                        vocabulary,
                    ),
                    domains=_restrict(
                        entry.domains, source_experience.domains, vocabulary
                    ),
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
        vocabulary: Optional[Set[str]] = None,
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

        result = self._assemble_projects(
            resume, plan, written, new_entries, vocabulary
        )

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
        vocabulary: Optional[Set[str]] = None,
    ) -> List[Project]:
        """Build the final project list, minting ids for generated entries."""
        by_id = {project.id: project for project in resume.projects}
        minted: List[str] = [project.id for project in resume.projects]
        pending_new = list(new_entries)
        ordered: List[Any] = []

        # Same rule as skills: each project the model actually wrote funds one
        # removal. Dropping a real project with nothing to show in its place
        # only makes the resume thinner.
        removal_budget = len(pending_new)

        for entry in plan.project_plans:
            if entry.action == PlanAction.REMOVE:
                if removal_budget > 0:
                    removal_budget -= 1
                    continue
                existing = by_id.get(entry.project_id)
                if existing is not None:
                    self.last_discarded.append(
                        f"project {existing.id} ({existing.name!r}): removal was "
                        "cancelled — no new project was generated to take its place"
                    )
                    ordered.append((entry.priority, existing.model_copy(deep=True)))
                continue

            if entry.action == PlanAction.GENERATE:
                if not pending_new:
                    break
                content = pending_new.pop(0)
                new_id = mint_id(PROJECT_PREFIX, minted)
                minted.append(new_id)
                ordered.append(
                    (entry.priority, Project(
                        id=new_id,
                        source=EntitySource.GENERATED,
                        name=content.name,
                        type=content.type,
                        # A repository URL cannot be invented.
                        repository=None,
                        # A generated project has no source terms to fall back
                        # on, so weak terms are simply dropped. A project with
                        # no technologies is valid; one listing "App Services"
                        # is just noise.
                        technologies=_filter_new(content.technologies, vocabulary),
                        domains=_filter_new(content.domains, vocabulary),
                        highlights=list(content.highlights),
                    ))
                )
                continue

            existing = by_id.get(entry.project_id)
            if existing is None:
                self.last_discarded.append(
                    f"project {entry.project_id} is not in the resume"
                )
                continue

            ordered.append(
                (entry.priority, self._apply_project(existing, entry, written, vocabulary))
            )

        # Most relevant first, so the Quality Gate can trim from the bottom.
        # sorted() is stable, so projects of equal priority keep plan order.
        ordered.sort(key=lambda pair: int(pair[0]))
        return [project for _, project in ordered]

    def _apply_project(
        self,
        existing: Project,
        entry: ProjectPlan,
        written: Dict[str, Any],
        vocabulary: Optional[Set[str]] = None,
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
            technologies=_restrict(
                content.technologies, existing.technologies, vocabulary
            ),
            domains=_restrict(content.domains, existing.domains, vocabulary),
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


def _restrict(
    terms: List[str],
    source_terms: List[str],
    vocabulary: Optional[Set[str]],
) -> List[str]:
    """
    Choose between the model's terms and the ones the resume already has.

    Three rules, applied per term, in order:

    1. **A term the resume already uses is always kept.** The candidate's own
       wording is theirs, and reordering it to emphasise what the job wants is
       exactly what tailoring means.
    2. **In strict mode, an unsupported term is dropped.** ``vocabulary`` holds
       everything the source resume supports and is ``None`` in aggressive
       mode, which skips this rule. Doing it here rather than leaving it to
       ``enforce_strict`` is deliberate: that check *raises*, discarding a
       whole 65-second generation over one stray label. Filtering makes the
       invalid state unreachable rather than merely detected, and
       ``enforce_strict`` stays as the backstop.
    3. **A term with no subject matter of its own is dropped, in both modes.**
       Swapping "SOC Platforms" for "Application Software Development" trades
       a specific fact for a phrase that could sit on any software resume. A
       job that names a real domain — "quota management", "threat
       intelligence" — passes this rule and the swap goes ahead; a job written
       entirely in process language offers no competitor for the slot, so the
       resume keeps what it had. See :mod:`src.vocabulary`.

    When any proposal is refused, the resume's own terms are retained
    alongside whatever survived. Refusing a proposal means declining the
    model's judgement about that term, so the sensible fallback is what the
    resume already said — not silence. Without this, a model proposing six
    empty phrases and one thin real one would leave the field holding only the
    thin one, which is worse than either the original or a clean swap.

    A response with nothing refused is trusted completely, which is what keeps
    genuine retargeting possible: a job that names real domains throughout
    replaces the resume's domains outright.
    """
    source_keys = normalised_set(source_terms)
    kept: List[str] = []
    refused = False

    for term in terms:
        if normalise(term) in source_keys:
            kept.append(term)
            continue
        if vocabulary is not None and not _supported(term, vocabulary):
            refused = True
            continue
        if is_weak_term(term):
            refused = True
            continue
        kept.append(term)

    if refused or not kept:
        present = normalised_set(kept)
        kept.extend(
            term for term in source_terms if normalise(term) not in present
        )

    return kept


def _supported(term: str, vocabulary: Set[str]) -> bool:
    """Return True when a term, or every word in it, is in the vocabulary."""
    normalised = " ".join(term.split()).casefold()
    if not normalised:
        return False
    if normalised in vocabulary:
        return True
    parts = normalised.split()
    return bool(parts) and all(part in vocabulary for part in parts)


def _filter_new(terms: List[str], vocabulary: Optional[Set[str]]) -> List[str]:
    """
    Filter terms for a newly generated entity, which has no source to fall
    back on.

    Same two rules as :func:`_restrict` — supported by the vocabulary, and not
    a weak phrase — but a refusal simply drops the term. A generated project
    with no technologies is valid; one listing "App Services" is noise, and one
    listing a technology named nowhere is a fabrication.
    """
    return [
        term
        for term in terms
        if not is_weak_term(term)
        and (vocabulary is None or _supported(term, vocabulary))
    ]


#: Weight given to a bullet carrying a quantified outcome, expressed in
#: job-term hits. Two means a metric outranks a bullet matching one job term
#: but yields to one matching three — a number is persuasive, not decisive.
METRIC_WEIGHT = 2


def _order_highlights(highlights: List[str], job_terms: List[str]) -> List[str]:
    """
    Order bullets strongest first, so the Quality Gate trims the weakest.

    The prompts already ask the model to do this. This is the enforcement,
    because "the prompt asked nicely" is not a guarantee and the bullet that
    falls off the bottom is a real loss.

    Two signals: how many of the job's own terms the bullet uses, and whether
    it carries a number. Nothing else — a longer bullet is not a better one.

    ``sorted`` is stable, so bullets scoring equally keep the order the model
    wrote them in. That matters: the model has context this scoring does not,
    and the intent is to correct clear mistakes, not to overrule its judgement
    everywhere.
    """
    if len(highlights) < 2:
        return list(highlights)

    terms = {t for t in job_terms if t}

    def rank(highlight: str) -> int:
        text = highlight.casefold()
        hits = sum(1 for term in terms if term in text)
        metric = METRIC_WEIGHT if contains_metric(highlight) else 0
        # Negated: sorted() ascends, and the strongest bullet must come first.
        return -(hits + metric)

    return sorted(highlights, key=rank)


def _source_capitalisations(resume: Resume) -> Set[str]:
    """
    Return every capitalised phrase the source resume uses.

    These are the candidate's own choices — job titles, product names, formal
    terms like "Security Operations Center" — and the capitalisation pass
    leaves them alone. The same reasoning as everywhere else in this module:
    the resume's own wording is never second-guessed, only the model's.
    """
    cased: Set[str] = set(capitalised_runs(resume.summary))
    for experience in resume.experiences:
        cased |= capitalised_runs(experience.role)
        for highlight in experience.highlights:
            cased |= capitalised_runs(highlight)
    for project in resume.projects:
        cased |= capitalised_runs(project.name)
        for highlight in project.highlights:
            cased |= capitalised_runs(highlight)
    return cased
