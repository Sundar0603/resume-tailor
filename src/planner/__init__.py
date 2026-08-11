"""
Resume Planner package.

Public API::

    from src.planner import ResumePlanner, ResumePlan
"""

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
    UnknownPlanningMode,
)
from .models import (
    ExperiencePlan,
    PlanAction,
    PlanningMode,
    ProjectPlan,
    ResumePlan,
    SectionPriority,
    SkillCategoryPlan,
    SummaryPlan,
)
from .planner import PLANNER_MAX_TOKENS, PLANNER_NUM_CTX, ResumePlanner, planner_options

__all__ = [
    "ResumePlanner",
    "ResumePlan",
    "SummaryPlan",
    "SkillCategoryPlan",
    "ExperiencePlan",
    "ProjectPlan",
    "PlanAction",
    "PlanningMode",
    "SectionPriority",
    "PlannerError",
    "InvalidPlannerJSON",
    "InvalidPlannerResponse",
    "ResumePlanValidationError",
    "UnknownPlanningMode",
    "PlanConsistencyError",
    "UnknownEntityReference",
    "DuplicatePlanEntry",
    "MissingPlanEntry",
    "ImmutableSectionViolation",
    "PlanningModeViolation",
    "canonicalize",
    "PLANNER_NUM_CTX",
    "PLANNER_MAX_TOKENS",
    "planner_options",
]
