"""
ResumePlanner — decides how a resume should be reshaped to fit a job analysis.

Responsibilities:
    - Build the planning prompt from a Resume and a JobAnalysis
    - Invoke the LLM provider with deterministic sampling parameters
    - Extract and parse the returned JSON
    - Canonicalize the parsed payload
    - Validate with Pydantic
    - Validate the resulting plan against the real resume (ids exist, every
      entity is covered, actions are internally consistent)
    - Return a ResumePlan

The planner never writes resume prose. It is stateless, side-effect free,
and must never mutate the Resume it is given.
"""

import json
from typing import Any, Dict, List

from pydantic import ValidationError

from src.analyzer._json_extract import extract_json_object
from src.analyzer.canonical import canonical_text
from src.analyzer.provider import LLMProvider
from src.analyzer.sampling import deterministic_options
from src.parser.models import Resume

from .canonical import canonicalize
from .exceptions import (
    DuplicatePlanEntry,
    ImmutableSectionViolation,
    InvalidPlannerJSON,
    InvalidPlannerResponse,
    MissingPlanEntry,
    PlanConsistencyError,
    PlannerError,
    PlanningModeViolation,
    ResumePlanValidationError,
    UnknownEntityReference,
)
from .models import PlanAction, PlanningMode, ResumePlan
from .prompts import build_planning_prompt

#: Resume + job analysis + the ~90-line planning schema. 8192 would truncate
#: the prompt on some Ollama runtimes.
PLANNER_NUM_CTX = 16384
PLANNER_MAX_TOKENS = 8192

#: Top-level keys the planner may never receive a plan for.
_IMMUTABLE_SECTION_KEYS = ("education_plan", "contact_plan", "metadata")


def planner_options() -> Dict[str, Any]:
    """Return the deterministic option set used for every planner request."""
    return deterministic_options(num_ctx=PLANNER_NUM_CTX, max_tokens=PLANNER_MAX_TOKENS)


class ResumePlanner:
    """
    Plans how a resume should be reshaped to fit a job analysis.

    Usage::

        planner = ResumePlanner(provider=my_provider)
        plan = planner.plan(resume, job_analysis)

    The planner is stateless. A single instance may be reused across calls.
    After a call to :meth:`plan`, :attr:`last_discarded` holds a human
    readable note for every skill removal that was silently dropped because
    it named a skill absent from its category — see rule 21 of the
    validation ruleset in ``tasks/011-resume-planner.md``.
    """

    def __init__(self, provider: LLMProvider) -> None:
        """
        Initialize the planner with an LLM provider.

        Parameters
        ----------
        provider : LLMProvider
            The LLM provider used to generate the plan.
        """
        self._provider = provider
        self.last_discarded: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(
        self,
        resume: Resume,
        job_analysis,
        mode: "PlanningMode | str" = PlanningMode.AGGRESSIVE,
    ) -> ResumePlan:
        """
        Plan how *resume* should be reshaped to fit *job_analysis*.

        Parameters
        ----------
        resume : Resume
            The parsed resume to plan against. Never mutated.
        job_analysis : JobAnalysis
            The structured job analysis to plan toward.
        mode : PlanningMode | str
            Controls how aggressively the planner may reshape the resume.
            Accepts an enum member or a case-insensitive string.

        Returns
        -------
        ResumePlan
            The validated plan.

        Raises
        ------
        UnknownPlanningMode
            If *mode* does not match any :class:`PlanningMode` member.
        InvalidPlannerResponse
            If the provider returns an empty or unexpected response.
        InvalidPlannerJSON
            If the provider response cannot be parsed as valid JSON.
        ImmutableSectionViolation
            If the response plans a section the planner may not change.
        ResumePlanValidationError
            If the parsed JSON does not conform to the ResumePlan schema.
        PlanConsistencyError
            If a schema-valid plan is inconsistent with the resume.
        PlannerError
            For any other planner-level failure.
        """
        self.last_discarded = []
        resolved = PlanningMode.parse(mode)

        prompt = build_planning_prompt(resume, job_analysis, resolved)
        raw_response = self._invoke_provider(prompt)
        data = canonicalize(self._parse_json(raw_response))

        self._reject_immutable_sections(data)

        plan = self._validate(data, resolved)
        self._validate_against_resume(plan, resume, resolved)
        return plan

    # ------------------------------------------------------------------
    # Private helpers — transport (mirrors JDAnalyzer)
    # ------------------------------------------------------------------

    def _invoke_provider(self, prompt: str) -> str:
        """Invoke the LLM provider and return the raw response string."""
        try:
            response = self._provider.generate(prompt, options=planner_options())
        except PlannerError:
            raise
        except Exception as exc:
            raise PlannerError(
                f"LLM provider raised an unexpected error: {exc}"
            ) from exc

        if not response or not response.strip():
            raise InvalidPlannerResponse("LLM provider returned an empty response.")

        return response.strip()

    def _parse_json(self, raw_response: str) -> dict:
        """Parse the raw response string into a dict."""
        try:
            return json.loads(extract_json_object(raw_response))
        except json.JSONDecodeError as exc:
            raise InvalidPlannerJSON(f"LLM response is not valid JSON: {exc}") from exc

    def _validate(self, data: dict, mode: PlanningMode) -> ResumePlan:
        """
        Validate the parsed dict against the ResumePlan schema.

        ``mode`` is set unconditionally from the resolved caller-requested
        mode, so a hallucinated ``mode`` field in the raw response cannot
        survive into the returned plan.
        """
        payload = dict(data)
        payload["mode"] = mode.value
        try:
            return ResumePlan(**payload)
        except ValidationError as exc:
            raise ResumePlanValidationError(
                f"LLM response does not conform to the ResumePlan schema: {exc}"
            ) from exc
        except TypeError as exc:
            raise ResumePlanValidationError(
                f"Unexpected data shape for ResumePlan: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers — planner-specific consistency checks
    # ------------------------------------------------------------------

    def _reject_immutable_sections(self, data: dict) -> None:
        """Raise ImmutableSectionViolation if the response plans a fixed section."""
        if not isinstance(data, dict):
            return
        for key in _IMMUTABLE_SECTION_KEYS:
            if key in data:
                raise ImmutableSectionViolation(
                    f"Plan may not include {key!r}: this section is immutable."
                )

    def _validate_against_resume(
        self, plan: ResumePlan, resume: Resume, mode: PlanningMode
    ) -> None:
        """Check the schema-valid plan for consistency with the real resume."""
        resume_experience_ids = {e.id for e in resume.experiences}
        resume_project_ids = {p.id for p in resume.projects}
        resume_category_ids = {c.id for c in resume.skills}

        self._check_duplicates(
            [ep.experience_id for ep in plan.experience_plans], "experience_id"
        )
        self._check_duplicates(
            [pp.project_id for pp in plan.project_plans if pp.project_id is not None],
            "project_id",
        )
        self._check_duplicates(
            [sp.category_id for sp in plan.skills_plans if sp.category_id is not None],
            "category_id",
        )

        for ep in plan.experience_plans:
            if ep.experience_id not in resume_experience_ids:
                raise UnknownEntityReference(
                    f"experience_plans: unknown experience_id {ep.experience_id!r}"
                )
        for pp in plan.project_plans:
            if pp.project_id is not None and pp.project_id not in resume_project_ids:
                raise UnknownEntityReference(
                    f"project_plans: unknown project_id {pp.project_id!r}"
                )
        for sp in plan.skills_plans:
            if sp.category_id is not None and sp.category_id not in resume_category_ids:
                raise UnknownEntityReference(
                    f"skills_plans: unknown category_id {sp.category_id!r}"
                )

        planned_experience_ids = {ep.experience_id for ep in plan.experience_plans}
        missing_experiences = resume_experience_ids - planned_experience_ids
        if missing_experiences:
            raise MissingPlanEntry(
                f"experience_plans: missing plan entry for {sorted(missing_experiences)}"
            )

        planned_project_ids = {
            pp.project_id for pp in plan.project_plans if pp.project_id is not None
        }
        missing_projects = resume_project_ids - planned_project_ids
        if missing_projects:
            raise MissingPlanEntry(
                f"project_plans: missing plan entry for {sorted(missing_projects)}"
            )

        planned_category_ids = {
            sp.category_id for sp in plan.skills_plans if sp.category_id is not None
        }
        missing_categories = resume_category_ids - planned_category_ids
        if missing_categories:
            raise MissingPlanEntry(
                f"skills_plans: missing plan entry for {sorted(missing_categories)}"
            )

        for sp in plan.skills_plans:
            self._reconcile_skill_lists(sp, resume, mode)

        if mode == PlanningMode.STRICT:
            self._check_no_generate(plan)

    def _check_duplicates(self, ids: List[str], label: str) -> None:
        seen = set()
        for entity_id in ids:
            if entity_id in seen:
                raise DuplicatePlanEntry(f"Duplicate {label}: {entity_id!r}")
            seen.add(entity_id)

    def _reconcile_skill_lists(
        self, sp, resume: Resume, mode: PlanningMode = PlanningMode.AGGRESSIVE
    ) -> None:
        """
        Drop skills_to_remove entries that name a skill absent from the
        category (rule 21 — a soft failure, noted via ``last_discarded``),
        and reject a skill listed in both skills_to_add and skills_to_remove
        of the same category (rule 22 — a hard failure).

        In strict mode, also drop skills_to_add entries naming something the
        candidate does not already demonstrate anywhere in the resume (rule 26).
        Strict mode forbids GENERATE, but nothing stopped a REWRITE from
        smuggling a brand-new skill in through skills_to_add — and the Resume
        Generator applies skill plans verbatim, so it would reach the resume as
        a claim the candidate never made.
        """
        add_keys = {canonical_text(s).casefold() for s in sp.skills_to_add}
        remove_keys = {canonical_text(s).casefold() for s in sp.skills_to_remove}
        overlap = add_keys & remove_keys
        if overlap:
            raise PlanConsistencyError(
                f"skills_plans[{sp.category_id!r}]: "
                f"skill(s) listed in both skills_to_add and skills_to_remove: "
                f"{sorted(overlap)}"
            )

        # A GENERATE entry is illegal in strict mode outright, and
        # _check_strict_mode reports that far more clearly than an emptied
        # skills_to_add would. Leave it alone and let that check fire.
        if (
            mode == PlanningMode.STRICT
            and sp.action != PlanAction.GENERATE
            and sp.skills_to_add
        ):
            supported = _supported_skill_vocabulary(resume)
            allowed = []
            for skill in sp.skills_to_add:
                if canonical_text(skill).casefold() in supported:
                    allowed.append(skill)
                else:
                    self.last_discarded.append(
                        f"{sp.category_id or 'new category'}: skill {skill!r} is not "
                        "supported by the resume (skills_to_add entry dropped in "
                        "STRICT mode)"
                    )
            sp.skills_to_add = allowed

        if sp.category_id is None:
            return

        category_skills = set()
        for category in resume.skills:
            if category.id == sp.category_id:
                category_skills = {
                    canonical_text(s).casefold() for s in category.skills
                }
                break

        kept = []
        for skill in sp.skills_to_remove:
            if canonical_text(skill).casefold() in category_skills:
                kept.append(skill)
            else:
                self.last_discarded.append(
                    f"{sp.category_id}: skill {skill!r} not found in category "
                    f"(skills_to_remove entry dropped)"
                )
        sp.skills_to_remove = kept

    def _check_no_generate(self, plan: ResumePlan) -> None:
        for sp in plan.skills_plans:
            if sp.action == PlanAction.GENERATE:
                raise PlanningModeViolation(
                    "STRICT mode forbids GENERATE, but skills_plans contains one."
                )
        for pp in plan.project_plans:
            if pp.action == PlanAction.GENERATE:
                raise PlanningModeViolation(
                    "STRICT mode forbids GENERATE, but project_plans contains one."
                )


def _supported_skill_vocabulary(resume: Resume) -> set:
    """
    Return every skill the resume already demonstrates, case-folded.

    Drawn from the skills section plus the technologies and domains named on
    experiences and projects. The wider net is deliberate: strict mode allows
    *reorganizing* existing information, so promoting a technology that only
    appears on a project into the skills section is legitimate. Inventing one
    that appears nowhere is not.
    """
    vocabulary = set()

    for category in resume.skills:
        vocabulary.update(canonical_text(s).casefold() for s in category.skills)
    for experience in resume.experiences:
        vocabulary.update(canonical_text(t).casefold() for t in experience.technologies)
        vocabulary.update(canonical_text(d).casefold() for d in experience.domains)
    for project in resume.projects:
        vocabulary.update(canonical_text(t).casefold() for t in project.technologies)
        vocabulary.update(canonical_text(d).casefold() for d in project.domains)

    vocabulary.discard("")
    return vocabulary
