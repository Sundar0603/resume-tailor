"""
Exceptions for the Resume Planner.
"""


class PlannerError(Exception):
    """Base exception for all planner errors."""


class InvalidPlannerResponse(PlannerError):
    """Raised when the LLM provider returns an unexpected or empty response."""


class InvalidPlannerJSON(PlannerError):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class ResumePlanValidationError(PlannerError):
    """Raised when the parsed JSON fails Pydantic schema validation."""


class UnknownPlanningMode(PlannerError):
    """Raised when the caller passes a planning mode that does not exist."""


class PlanConsistencyError(PlannerError):
    """Raised when a schema-valid plan is inconsistent with the resume."""


class UnknownEntityReference(PlanConsistencyError):
    """Raised when a plan entry references an id absent from the resume."""


class DuplicatePlanEntry(PlanConsistencyError):
    """Raised when a plan contains more than one entry for the same id."""


class MissingPlanEntry(PlanConsistencyError):
    """Raised when a resume entity has no corresponding plan entry."""


class ImmutableSectionViolation(PlanConsistencyError):
    """Raised when a plan attempts to touch a section the planner may not change."""


class PlanningModeViolation(PlanConsistencyError):
    """Raised when a plan violates the rules of its own planning mode."""
