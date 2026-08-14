"""
Shared fixtures for the Resume Generator test suite.

Fakes subclass the ``LLMProvider`` ABC; the suite does not use
``unittest.mock``. Factories deep-copy on the way out so a test may mutate its
own copy freely.

The Generator makes up to three calls per generation — summary, experiences,
projects — always in that order, and skips a call entirely when the plan has
nothing for that section. ``SequencedProvider`` exists for that: it answers
each call from a queue rather than returning one canned string.
"""

import copy
import json
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
from src.planner.models import ResumePlan


class FakeProvider(LLMProvider):
    """LLM provider that returns the same response for every call."""

    def __init__(self, response: str) -> None:
        self._response = response

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._response


class FailingProvider(LLMProvider):
    """LLM provider that always raises."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise self._exc


class SequencedProvider(LLMProvider):
    """
    LLM provider that answers each call from a queue, recording as it goes.

    Raises ``AssertionError`` when called more times than it has responses —
    an unexpected extra call is a bug worth failing loudly on, not one to
    paper over with a repeated answer.
    """

    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self.prompts: List[str] = []
        self.options: List[Optional[Dict[str, Any]]] = []

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.prompts.append(prompt)
        self.options.append(options)
        if not self._responses:
            raise AssertionError(
                f"SequencedProvider called {len(self.prompts)} times but was "
                "given fewer responses."
            )
        return self._responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self.prompts)


# ---------------------------------------------------------------------------
# Resume / analysis fixtures
# ---------------------------------------------------------------------------


def make_resume() -> Resume:
    """
    A resume shaped like a real one.

    Two experiences (the validator requires exactly two), two projects (it
    requires at least two), two skill categories, one education entry. The
    numbers in the highlights are load-bearing for the strict-mode metric
    tests.
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
        # At least 20 words, so the baseline generation produces no validator
        # warnings and a test asserting "no warnings" means something.
        summary=(
            "Backend engineer with four years of experience building scalable "
            "services in Python and Go, focused on payments and observability, "
            "with a track record of shipping reliable systems."
        ),
        skills=[
            SkillCategory(
                id="skill_001", category="Languages", skills=["Python", "Go"]
            ),
            SkillCategory(id="skill_002", category="Cloud", skills=["AWS", "Docker"]),
        ],
        experiences=[
            Experience(
                id="exp_001",
                company="Acme Corp",
                role="Software Engineering Intern",
                employment_type="Internship",
                duration="Summer 2021",
                location="Remote",
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
                location="Chennai",
                technologies=["Python", "Go"],
                domains=["Backend", "Cloud"],
                highlights=[
                    "Shipped a payments service handling 10000 requests per second.",
                    "Reduced API latency by 30% through query optimization.",
                ],
            ),
        ],
        projects=[
            Project(
                id="proj_001",
                name="Task Tracker",
                type="Personal",
                repository="github.com/janedoe/task-tracker",
                technologies=["Python"],
                domains=["Tooling"],
                highlights=["Built a CLI task tracker."],
            ),
            Project(
                id="proj_002",
                name="Chat App",
                type="Personal",
                technologies=["Go"],
                domains=["Realtime"],
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


# ---------------------------------------------------------------------------
# Plan fixtures
# ---------------------------------------------------------------------------


def make_plan_payload(**overrides: Any) -> Dict[str, Any]:
    """
    A valid all-KEEP plan for :func:`make_resume`, deep-copied on every call.

    All-KEEP is the useful baseline: it needs no LLM call at all, so a test
    that overrides one section is testing exactly that section.
    """
    payload: Dict[str, Any] = {
        "mode": "AGGRESSIVE",
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
                "action": "KEEP",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Already aligned with the target role.",
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
                "reasoning": "Demonstrates Python tooling.",
            },
            {
                "project_id": "proj_002",
                "action": "KEEP",
                "priority": "MEDIUM",
                "rewrite_strategy": None,
                "generation_brief": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Demonstrates Go and realtime work.",
            },
        ],
    }
    payload.update(copy.deepcopy(overrides))
    return copy.deepcopy(payload)


def make_plan(**overrides: Any) -> ResumePlan:
    """Return a validated ResumePlan built from :func:`make_plan_payload`."""
    return ResumePlan(**make_plan_payload(**overrides))


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def summary_response(summary: str) -> str:
    return json.dumps({"summary": summary})


def experiences_response(*entries: Dict[str, Any]) -> str:
    return json.dumps({"experiences": list(entries)})


def projects_response(*entries: Dict[str, Any]) -> str:
    return json.dumps({"projects": list(entries)})


def experience_entry(experience_id: str, **overrides: Any) -> Dict[str, Any]:
    entry = {
        "experience_id": experience_id,
        "role": "Software Engineer",
        "technologies": ["Python", "Go"],
        "domains": ["Backend"],
        "highlights": ["Shipped a payments service."],
    }
    entry.update(overrides)
    return entry


def project_entry(project_id: Optional[str], **overrides: Any) -> Dict[str, Any]:
    entry = {
        "project_id": project_id,
        "name": "Task Tracker",
        "type": "Personal",
        "technologies": ["Python"],
        "domains": ["Tooling"],
        "highlights": ["Built a CLI task tracker."],
    }
    entry.update(overrides)
    return entry
