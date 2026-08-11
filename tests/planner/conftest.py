"""
Shared fixtures for the Resume Planner test suite.

No fixture files: negative tests are one-line mutations of ``make_payload()``.
"""

import copy
from typing import Any, Dict, List, Optional

from src.analyzer.models import JobAnalysis
from src.analyzer.provider import LLMProvider
from src.parser.models import (
    Contact,
    Education,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)


class FakeProvider(LLMProvider):
    """LLM provider that returns a pre-configured response string."""

    def __init__(self, response: str) -> None:
        self._response = response

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._response


class FailingProvider(LLMProvider):
    """LLM provider that always raises an exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise self._exc


class CapturingProvider(LLMProvider):
    """LLM provider that records the prompt and options it was called with."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: List[str] = []
        self.options: List[Optional[Dict[str, Any]]] = []

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.prompts.append(prompt)
        self.options.append(options)
        return self._response


def make_resume() -> Resume:
    """
    A resume shaped like a real one: one company, two roles, two projects,
    two skill categories, one education entry.
    """
    return Resume(
        metadata=Metadata(resume="jane-doe", template="default", version="1.0"),
        contact=Contact(
            name="Jane Doe",
            phone="555-0100",
            email="jane.doe@example.com",
            linkedin="linkedin.com/in/janedoe",
            github="github.com/janedoe",
        ),
        summary="Backend engineer with experience building scalable services.",
        skills=[
            SkillCategory(id="skill_001", category="Languages", skills=["Python", "Go"]),
            SkillCategory(id="skill_002", category="Cloud", skills=["AWS", "Docker"]),
        ],
        experiences=[
            Experience(
                id="exp_001",
                company="Acme Corp",
                role="Software Engineering Intern",
                employment_type="Internship",
                duration="Summer 2021",
                technologies=["Python"],
                domains=["Backend"],
                highlights=["Built an internal reporting tool."],
            ),
            Experience(
                id="exp_002",
                company="Acme Corp",
                role="Software Engineer",
                employment_type="Full-time",
                duration="2021 - Present",
                technologies=["Python", "Go"],
                domains=["Backend", "Cloud"],
                highlights=[
                    "Shipped a payments service handling 10k requests/sec.",
                    "Reduced API latency by 30% through query optimization.",
                ],
            ),
        ],
        projects=[
            Project(
                id="proj_001",
                name="Task Tracker",
                type="Personal",
                technologies=["Python"],
                highlights=["Built a CLI task tracker."],
            ),
            Project(
                id="proj_002",
                name="Chat App",
                type="Personal",
                technologies=["Go"],
                highlights=["Built a real-time chat server."],
            ),
        ],
        education=[
            Education(
                id="edu_001",
                institution="State University",
                degree="B.S.",
                major="Computer Science",
                duration="2017 - 2021",
            )
        ],
    )


def make_job_analysis() -> JobAnalysis:
    return JobAnalysis(
        company="Globex",
        role="Backend Engineer",
        seniority="Mid",
        required_skills=["Python", "AWS"],
        preferred_skills=["Go"],
        technologies=["Docker", "AWS"],
        domains=["Backend"],
        responsibilities=["Design and operate backend services."],
        qualifications=["3+ years of experience"],
        nice_to_have=["Experience with Go"],
        keywords=["Python", "AWS", "Backend"],
    )


def make_payload(**overrides: Any) -> Dict[str, Any]:
    """
    A valid planner response payload for :func:`make_resume`, deep-copied on
    every call so tests may mutate their own copy freely.
    """
    payload = {
        "summary_plan": {
            "action": "KEEP",
            "priority": "MEDIUM",
            "reasoning": "Summary already reflects backend focus.",
            "keywords_to_include": [],
        },
        "skills_plans": [
            {
                "category_id": "skill_001",
                "action": "KEEP",
                "priority": "MEDIUM",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Languages already match the job analysis.",
            },
            {
                "category_id": "skill_002",
                "action": "KEEP",
                "priority": "MEDIUM",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Cloud skills already match the job analysis.",
            },
        ],
        "experience_plans": [
            {
                "experience_id": "exp_001",
                "action": "KEEP",
                "priority": "LOW",
                "rewrite_strategy": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Internship is less relevant than the full-time role.",
            },
            {
                "experience_id": "exp_002",
                "action": "REWRITE",
                "priority": "CRITICAL",
                "rewrite_strategy": "Emphasize backend service ownership and scale.",
                "keywords_to_include": ["Python", "AWS"],
                "themes_to_emphasize": ["ownership", "scale"],
                "reasoning": "This is the most relevant role for the job analysis.",
            },
        ],
        "project_plans": [
            {
                "project_id": "proj_001",
                "action": "KEEP",
                "priority": "MEDIUM",
                "rewrite_strategy": None,
                "generation_brief": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Demonstrates independent backend work.",
            },
            {
                "project_id": "proj_002",
                "action": "REMOVE",
                "priority": "LOW",
                "rewrite_strategy": None,
                "generation_brief": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Not relevant to the job analysis.",
            },
        ],
    }
    payload.update(copy.deepcopy(overrides))
    return copy.deepcopy(payload)
