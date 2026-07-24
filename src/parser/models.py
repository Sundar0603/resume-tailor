"""
Domain models for the Resume Tailor parser.

These dataclasses represent the in-memory structure of a parsed resume.
They are pure data containers — no validation, no rendering logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Metadata:
    resume: str
    template: str
    version: str


@dataclass
class Contact:
    name: str
    phone: str
    email: str
    linkedin: str
    github: str


@dataclass
class SkillCategory:
    category: str
    skills: List[str] = field(default_factory=list)


@dataclass
class Experience:
    company: str
    role: str
    employment_type: str
    duration: str
    location: Optional[str] = None
    technologies: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)


@dataclass
class Project:
    name: str
    type: str
    repository: Optional[str] = None
    technologies: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)


@dataclass
class Education:
    institution: str
    degree: str
    major: str
    duration: str
    cgpa: Optional[str] = None
    location: Optional[str] = None


@dataclass
class Resume:
    metadata: Metadata
    contact: Contact
    summary: str
    skills: List[SkillCategory] = field(default_factory=list)
    experiences: List[Experience] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
