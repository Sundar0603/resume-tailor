"""
Per-section response models for the Resume Generator.

These describe what the LLM is asked to return, not what the Generator
returns. The Generator returns a :class:`src.parser.models.Resume`, assembled
in Python from these fragments.

The split matters: the model supplies prose and the identity of the entity the
prose belongs to, and nothing else. Entity IDs, ``EntitySource`` values, plan
actions and modes are application metadata, minted and imposed by the
Generator. A model that could set them could quietly relabel a fabricated
project as canonical.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    """The rewritten professional summary."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    summary: str


class ExperienceContent(BaseModel):
    """Rewritten content for one existing work experience."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    experience_id: str
    role: str
    technologies: List[str] = []
    domains: List[str] = []
    highlights: List[str] = []


class ExperienceResponse(BaseModel):
    """Rewritten content for every experience the plan marked REWRITE."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    experiences: List[ExperienceContent] = []


class ProjectContent(BaseModel):
    """
    Content for one project.

    ``project_id`` is the id of an existing project being rewritten, or
    ``None`` for a newly generated one. The Generator mints the real id; a
    value invented by the model is never trusted.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    project_id: Optional[str] = None
    name: str
    type: str
    technologies: List[str] = []
    domains: List[str] = []
    highlights: List[str] = []


class ProjectResponse(BaseModel):
    """Content for every project the plan marked REWRITE or GENERATE."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    projects: List[ProjectContent] = []
