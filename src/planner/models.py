"""
Domain models for the Resume Planner.

A :class:`ResumePlan` is a structured set of decisions describing what should
change in a resume and why, without ever writing resume prose itself. Every
entry references a resume entity by id so the plan can be validated against
the real :class:`~src.parser.models.Resume` before it is trusted.
"""

from enum import Enum, IntEnum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PlanAction(str, Enum):
    """A decision applied to a resume section or entity."""

    KEEP = "KEEP"
    REWRITE = "REWRITE"
    REMOVE = "REMOVE"
    GENERATE = "GENERATE"


class PlanningMode(str, Enum):
    """Controls how aggressively the planner may reshape a resume."""

    AGGRESSIVE = "AGGRESSIVE"
    STRICT = "STRICT"

    @classmethod
    def parse(cls, mode: "PlanningMode | str") -> "PlanningMode":
        """
        Resolve a mode passed as an enum member or a case-insensitive string.

        Raises
        ------
        UnknownPlanningMode
            If *mode* does not match any :class:`PlanningMode` member.
        """
        from .exceptions import UnknownPlanningMode

        if isinstance(mode, cls):
            return mode
        if isinstance(mode, str):
            try:
                return cls(mode.strip().upper())
            except ValueError:
                pass
        raise UnknownPlanningMode(f"Unknown planning mode: {mode!r}")


class SectionPriority(IntEnum):
    """Relative importance of a plan entry, most important first."""

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


#: Actions permitted on the summary section.
SUMMARY_ACTIONS = {PlanAction.KEEP, PlanAction.REWRITE}

#: Actions permitted on an experience entry.
EXPERIENCE_ACTIONS = {PlanAction.KEEP, PlanAction.REWRITE}

#: Actions permitted on a project entry.
PROJECT_ACTIONS = {
    PlanAction.KEEP,
    PlanAction.REWRITE,
    PlanAction.REMOVE,
    PlanAction.GENERATE,
}

#: Actions permitted on a skill category entry.
SKILL_CATEGORY_ACTIONS = {
    PlanAction.KEEP,
    PlanAction.REWRITE,
    PlanAction.REMOVE,
    PlanAction.GENERATE,
}

#: Maps a member name to its value so ``SectionPriority("CRITICAL")`` works.
#: ``IntEnum`` only accepts the underlying int by default; a
#: ``mode="before"`` validator on every plan model routes names through this
#: map first and passes anything else through untouched, so Pydantic still
#: reports the real error for a genuinely bad value.
_PRIORITY_NAMES = {member.name: member.value for member in SectionPriority}


def _coerce_priority(value: object) -> object:
    """Map a priority name to its int value; pass anything else through."""
    if isinstance(value, str) and value.strip().upper() in _PRIORITY_NAMES:
        return _PRIORITY_NAMES[value.strip().upper()]
    return value


def _validate_action(action: PlanAction, allowed: set, section: str) -> PlanAction:
    if action not in allowed:
        allowed_names = ", ".join(sorted(a.value for a in allowed))
        raise ValueError(
            f"{section}: action {action.value!r} is not allowed here "
            f"(allowed: {allowed_names})"
        )
    return action


class SummaryPlan(BaseModel):
    """The plan for the resume summary section."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action: PlanAction
    priority: SectionPriority
    reasoning: str
    keywords_to_include: List[str] = []

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority_name(cls, value: object) -> object:
        return _coerce_priority(value)

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: PlanAction) -> PlanAction:
        return _validate_action(value, SUMMARY_ACTIONS, "summary_plan")

    @field_validator("reasoning")
    @classmethod
    def _check_reasoning(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("summary_plan: reasoning must not be empty")
        return value

    @model_validator(mode="after")
    def _check_rewrite_strategy_not_applicable(self) -> "SummaryPlan":
        return self


class SkillCategoryPlan(BaseModel):
    """The plan for one skill category — existing or newly generated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    category_id: Optional[str] = None
    action: PlanAction
    priority: SectionPriority
    new_category_name: Optional[str] = None
    skills_to_add: List[str] = []
    skills_to_remove: List[str] = []
    reasoning: str

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority_name(cls, value: object) -> object:
        return _coerce_priority(value)

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: PlanAction) -> PlanAction:
        return _validate_action(value, SKILL_CATEGORY_ACTIONS, "skills_plans")

    @field_validator("reasoning")
    @classmethod
    def _check_reasoning(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("skills_plans: reasoning must not be empty")
        return value

    @model_validator(mode="after")
    def _check_generate_pairing(self) -> "SkillCategoryPlan":
        if self.action == PlanAction.GENERATE:
            if self.category_id is not None:
                raise ValueError(
                    "skills_plans: GENERATE requires category_id to be null"
                )
            if not self.new_category_name or not self.new_category_name.strip():
                raise ValueError(
                    "skills_plans: GENERATE requires a non-empty new_category_name"
                )
            # A generated category is applied verbatim by the Resume Generator,
            # which makes no LLM call for skills. Without this rule a category
            # can be created with a name and no members: the validator only
            # warns about an empty category (EMPTY_SKILL_CATEGORY), so it would
            # reach the rendered resume.
            if not self.skills_to_add:
                raise ValueError(
                    "skills_plans: GENERATE requires a non-empty skills_to_add"
                )
        else:
            if not self.category_id or not self.category_id.strip():
                raise ValueError(
                    f"skills_plans: {self.action.value} requires a non-empty category_id"
                )
            # REWRITE may rename the category so its heading can match the
            # language of the job description — "Backend" becoming "Backend &
            # Distributed Systems". KEEP and REMOVE never rename.
            if (
                self.action != PlanAction.REWRITE
                and self.new_category_name is not None
            ):
                raise ValueError(
                    f"skills_plans: {self.action.value} must not set new_category_name"
                )
            if self.action == PlanAction.REWRITE and self.new_category_name is not None:
                if not self.new_category_name.strip():
                    raise ValueError(
                        "skills_plans: REWRITE new_category_name must not be blank"
                    )
        return self


class ExperiencePlan(BaseModel):
    """The plan for one existing experience entry."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    experience_id: str
    action: PlanAction
    priority: SectionPriority
    rewrite_strategy: Optional[str] = None
    keywords_to_include: List[str] = []
    themes_to_emphasize: List[str] = []
    reasoning: str

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority_name(cls, value: object) -> object:
        return _coerce_priority(value)

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: PlanAction) -> PlanAction:
        return _validate_action(value, EXPERIENCE_ACTIONS, "experience_plans")

    @field_validator("experience_id")
    @classmethod
    def _check_experience_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("experience_plans: experience_id must not be empty")
        return value

    @field_validator("reasoning")
    @classmethod
    def _check_reasoning(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("experience_plans: reasoning must not be empty")
        return value

    @model_validator(mode="after")
    def _check_rewrite_strategy(self) -> "ExperiencePlan":
        if self.action == PlanAction.REWRITE:
            if not self.rewrite_strategy or not self.rewrite_strategy.strip():
                raise ValueError(
                    "experience_plans: REWRITE requires a non-empty rewrite_strategy"
                )
        else:
            if self.rewrite_strategy is not None:
                raise ValueError(
                    f"experience_plans: {self.action.value} must not set rewrite_strategy"
                )
        return self


class ProjectPlan(BaseModel):
    """The plan for one project entry — existing or newly generated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    project_id: Optional[str] = None
    action: PlanAction
    priority: SectionPriority
    rewrite_strategy: Optional[str] = None
    generation_brief: Optional[str] = None
    keywords_to_include: List[str] = []
    themes_to_emphasize: List[str] = []
    reasoning: str

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority_name(cls, value: object) -> object:
        return _coerce_priority(value)

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: PlanAction) -> PlanAction:
        return _validate_action(value, PROJECT_ACTIONS, "project_plans")

    @field_validator("reasoning")
    @classmethod
    def _check_reasoning(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("project_plans: reasoning must not be empty")
        return value

    @model_validator(mode="after")
    def _check_generate_pairing(self) -> "ProjectPlan":
        if self.action == PlanAction.GENERATE:
            if self.project_id is not None:
                raise ValueError(
                    "project_plans: GENERATE requires project_id to be null"
                )
            if not self.generation_brief or not self.generation_brief.strip():
                raise ValueError(
                    "project_plans: GENERATE requires a non-empty generation_brief"
                )
        else:
            if not self.project_id or not self.project_id.strip():
                raise ValueError(
                    f"project_plans: {self.action.value} requires a non-empty project_id"
                )
            if self.generation_brief is not None:
                raise ValueError(
                    f"project_plans: {self.action.value} must not set generation_brief"
                )

        if self.action == PlanAction.REWRITE:
            if not self.rewrite_strategy or not self.rewrite_strategy.strip():
                raise ValueError(
                    "project_plans: REWRITE requires a non-empty rewrite_strategy"
                )
        else:
            if self.rewrite_strategy is not None:
                raise ValueError(
                    f"project_plans: {self.action.value} must not set rewrite_strategy"
                )
        return self


class ResumePlan(BaseModel):
    """
    The complete set of planning decisions for one resume/job-analysis pair.

    ``mode`` is injected by :class:`~src.planner.planner.ResumePlanner` after
    validation, not requested from the LLM — a hallucinated mode value in the
    raw response cannot survive into the returned plan.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: PlanningMode = PlanningMode.AGGRESSIVE
    summary_plan: SummaryPlan
    skills_plans: List[SkillCategoryPlan] = []
    experience_plans: List[ExperiencePlan] = []
    project_plans: List[ProjectPlan] = []
