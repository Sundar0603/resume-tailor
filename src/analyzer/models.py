"""
Domain models for the Job Description Analyzer.

JobAnalysis is a pure data container representing the structured output
of analyzing a raw job description.
No scoring, recommendations, or AI reasoning is included.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class JobAnalysis(BaseModel):
    """
    Structured representation of a analyzed job description.

    Contains only information required by downstream resume generation.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    company: Optional[str] = None
    role: str
    seniority: Optional[str] = None
    summary: str
    required_skills: List[str]
    preferred_skills: List[str] = []
    technologies: List[str] = []
    domains: List[str] = []
    responsibilities: List[str] = []
    qualifications: List[str] = []
    nice_to_have: List[str] = []
    keywords: List[str]
