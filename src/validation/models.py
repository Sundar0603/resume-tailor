"""
Validation models for the Resume Validator.

Contains ValidationResult and ValidationIssue.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict

from .codes import ValidationCode


class ValidationIssue(BaseModel):
    """Represents a single validation issue found during resume validation."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    code: ValidationCode
    message: str
    entity_id: Optional[str] = None
    field: Optional[str] = None


class ValidationResult(BaseModel):
    """Represents the outcome of a resume validation run."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    is_valid: bool = True
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    info: List[ValidationIssue] = []
