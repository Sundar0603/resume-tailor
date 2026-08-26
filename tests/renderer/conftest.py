"""
Shared factories for the renderer tests.

Plain factory functions rather than pytest fixtures, matching the analyzer,
planner and generator suites. Factories deep-copy on the way out, so a test
that mutates what it is given cannot leak into the next one.

``semantically_equal`` exists because strict Pydantic equality is the wrong
test for anything the Generator produced: ``id`` and ``source`` are
runtime-only, never appear in Markdown, and are regenerated on every parse.
"""

import copy
from typing import Any, Dict, List

from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)

CANONICAL_RESUMES = [
    "content/backend_resume.md",
    "content/cybersecurity_resume.md",
    "content/fullstack_resume.md",
]

_RUNTIME_FIELDS = ("id", "source")


def make_resume(**overrides: Any) -> Resume:
    """Return a complete, schema-valid resume with every optional field set."""
    resume = Resume(
        metadata=Metadata(resume="backend", template="backend", version="1.0"),
        contact=Contact(
            name="Sundar S",
            phone="+91 7397398343",
            email="sundars0603@gmail.com",
            linkedin="https://www.linkedin.com/in/sundar-s-870042235/",
            github="https://github.com/Sundar0603",
        ),
        summary=(
            "Backend Software Engineer with 2 years of experience at Zoho "
            "building enterprise-scale platforms using Java and Redis."
        ),
        skills=[
            SkillCategory(id="skill_001", category="Security",
                          skills=["SOC Tooling", "Threat Intelligence"]),
            SkillCategory(id="skill_002", category="Backend",
                          skills=["Spring Boot", "Redis"]),
        ],
        experiences=[
            Experience(
                id="exp_001",
                company="Zoho Corporation",
                role="Software Developer",
                employment_type="Full Time",
                duration="May 2024 - Present",
                location="Chennai",
                technologies=["Java", "Spring Boot"],
                domains=["Threat Intelligence", "API Security"],
                highlights=["Built ingestion pipelines.", "Designed workflows."],
            ),
            Experience(
                id="exp_002",
                company="Zoho Corporation",
                role="Project Trainee",
                employment_type="Internship",
                duration="Dec 2023 - Apr 2024",
                location="Chennai",
                technologies=["Java"],
                domains=["Rule Management"],
                highlights=["Implemented rule evaluation."],
            ),
        ],
        projects=[
            Project(
                id="proj_001",
                name="Triage Studio",
                type="Personal",
                repository="https://github.com/Sundar0603/triage-studio",
                technologies=["Python", "OpenAI APIs"],
                domains=["AI Agents", "Security"],
                highlights=["Built an agent loop.", "Developed a triage UI."],
            ),
            Project(
                id="proj_002",
                name="SOCrates",
                type="Personal",
                technologies=["Java"],
                domains=["Security"],
                highlights=["Automated alert enrichment."],
            ),
        ],
        education=[
            Education(
                id="edu_001",
                institution="Anna University",
                degree="B.E.",
                major="Computer Science and Engineering",
                duration="2020 - 2024",
                cgpa="9.18",
                location="Chennai",
            )
        ],
    )
    for field, value in overrides.items():
        setattr(resume, field, value)
    return copy.deepcopy(resume)


def make_sparse_resume() -> Resume:
    """
    Return a resume with every optional field absent.

    No file in ``content/`` exercises a missing ``location``, ``cgpa`` or
    ``repository``, so optional-field omission has no canonical fixture.
    """
    resume = make_resume()
    for experience in resume.experiences:
        experience.location = None
        experience.technologies = []
        experience.domains = []
    for project in resume.projects:
        project.repository = None
        project.technologies = []
        project.domains = []
    for entry in resume.education:
        entry.cgpa = None
        entry.location = None
    return resume


def make_generated_resume() -> Resume:
    """
    Return a resume shaped like Generator output.

    Carries ``source=GENERATED`` and a sparse id sequence, both of which the
    Generator produces legitimately and neither of which survives a round
    trip. Used to prove the serializer copes and the loss is confined to
    runtime fields.
    """
    resume = make_resume()
    resume.projects[0].id = "proj_002"
    resume.projects[0].source = EntitySource.GENERATED
    resume.projects[1].id = "proj_005"
    resume.skills[1].id = "skill_004"
    resume.skills[1].source = EntitySource.GENERATED
    return resume


def semantic_dump(resume: Resume) -> Dict[str, Any]:
    """Dump a resume with runtime-only fields (``id``, ``source``) removed."""
    data = resume.model_dump()
    for key in ("skills", "experiences", "projects", "education"):
        for entity in data[key]:
            for field in _RUNTIME_FIELDS:
                entity.pop(field, None)
    return data


def semantically_equal(left: Resume, right: Resume) -> bool:
    """Compare two resumes ignoring runtime-only fields."""
    return semantic_dump(left) == semantic_dump(right)


def section_order(markdown: str) -> List[str]:
    """Return the H1 headings of a document, in the order they appear."""
    return [
        line[2:].strip()
        for line in markdown.splitlines()
        if line.startswith("# ")
    ]
