"""
Domain models for the Resume Tailor parser.

These Pydantic models represent the in-memory structure of a parsed resume.
They are pure data containers — no validation, no rendering logic.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class Metadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    resume: str
    template: str
    version: str


class Contact(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    name: str
    phone: str
    email: str
    linkedin: str
    github: str


class SkillCategory(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str = ""
    category: str
    skills: List[str] = []

    def skill_count(self) -> int:
        """Return the number of skills in this category."""
        return len(self.skills)


class Experience(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str = ""
    company: str
    role: str
    employment_type: str
    duration: str
    location: Optional[str] = None
    technologies: List[str] = []
    domains: List[str] = []
    highlights: List[str] = []

    def word_count(self) -> int:
        """Return the total number of words across all highlight bullets."""
        return sum(len(h.split()) for h in self.highlights)


class Project(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str = ""
    name: str
    type: str
    repository: Optional[str] = None
    technologies: List[str] = []
    domains: List[str] = []
    highlights: List[str] = []

    def word_count(self) -> int:
        """Return the total number of words across all highlight bullets."""
        return sum(len(h.split()) for h in self.highlights)


class Education(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str = ""
    institution: str
    degree: str
    major: str
    duration: str
    cgpa: Optional[str] = None
    location: Optional[str] = None


class Resume(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    metadata: Metadata
    contact: Contact
    summary: str
    skills: List[SkillCategory] = []
    experiences: List[Experience] = []
    projects: List[Project] = []
    education: List[Education] = []

    # ------------------------------------------------------------------
    # Skills helpers
    # ------------------------------------------------------------------

    def get_skills(self, category: str) -> List[str]:
        """Return all skills belonging to the given category name."""
        for sc in self.skills:
            if sc.category == category:
                return list(sc.skills)
        return []

    def all_skills(self) -> List[str]:
        """Return a flattened list of every skill across all categories."""
        return [skill for sc in self.skills for skill in sc.skills]

    def total_skills(self) -> int:
        """Return the total number of individual skills."""
        return sum(sc.skill_count() for sc in self.skills)

    # ------------------------------------------------------------------
    # Count helpers
    # ------------------------------------------------------------------

    def total_experiences(self) -> int:
        """Return the total number of experiences."""
        return len(self.experiences)

    def total_projects(self) -> int:
        """Return the total number of projects."""
        return len(self.projects)

    def total_education(self) -> int:
        """Return the total number of education entries."""
        return len(self.education)

    def total_highlights(self) -> int:
        """Return the total number of highlight bullets across experiences and projects."""
        exp_highlights = sum(len(e.highlights) for e in self.experiences)
        proj_highlights = sum(len(p.highlights) for p in self.projects)
        return exp_highlights + proj_highlights

    # ------------------------------------------------------------------
    # Word count
    # ------------------------------------------------------------------

    def word_count(self) -> int:
        """Return the approximate total number of words in summary, experience highlights, and project highlights."""
        summary_words = len(self.summary.split())
        exp_words = sum(e.word_count() for e in self.experiences)
        proj_words = sum(p.word_count() for p in self.projects)
        return summary_words + exp_words + proj_words
