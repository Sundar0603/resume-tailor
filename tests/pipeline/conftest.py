"""
Shared factories for the end-to-end pipeline tests.

The point of these tests is the *chain*: every stage is already covered in
isolation, so what is untested is whether one stage's output is actually
accepted by the next. That is exactly the kind of break that survives 1000
green unit tests, so it needs to run offline on every change.

``ScriptedProvider`` therefore stands in for the LLM. It dispatches on a marker
in the prompt and returns a canned reply for each of the five calls a run makes
— analyze, plan, and up to three generate calls. The replies are *derived from
the source resume* rather than hardcoded, so they cannot drift out of sync with
the fixtures the way a pasted transcript would.

No ``unittest.mock`` anywhere, matching the rest of the suite: this is a
hand-written subclass of the real ``LLMProvider`` ABC.
"""

import json
from typing import Any, Dict, List, Optional

from src.analyzer.provider import LLMProvider
from src.parser.models import Resume

# Markers unique to each prompt, verified against the real builders.
ANALYSIS_MARKER = "job description analysis assistant"
PLAN_MARKER = "resume planning assistant"
SUMMARY_MARKER = '"summary": "<the rewritten summary>"'
# Taken from each prompt's *response schema*, not its body: the resume context
# embedded in all three generator prompts contains both "experiences": [ and
# "projects": [, so those keys do not discriminate.
EXPERIENCES_MARKER = '"experience_id": "<the id given in the plan>"'
PROJECTS_MARKER = '"project_id": "<the id given in the plan, or null'
#: The Revision Engine's compression prompt. Sourced from the prompt module
#: itself (``src.revision.prompts.response_markers``) so this fixture cannot
#: drift out of step with the prompt it is meant to recognise.
COMPRESSION_MARKER = "resume compression assistant"

# 20-120 words, per the generator's hard budget.
REWRITTEN_SUMMARY = (
    "Backend Software Engineer with 2 years of experience at Zoho building "
    "enterprise-scale Security Operations Center platforms using Java, Spring "
    "Boot, Redis and MySQL. Designs distributed workflows and scalable backend "
    "services supporting security investigations, automated incident "
    "management and high-throughput data processing across production systems."
)


def job_analysis_payload() -> Dict[str, Any]:
    """A JobAnalysis reply, flat by design so it can be compared."""
    return {
        "company": "Acme",
        "role": "Backend Engineer",
        "seniority": "Mid",
        "required_skills": ["Java", "Spring Boot"],
        "preferred_skills": ["Redis"],
        "technologies": ["Java", "Spring Boot", "MySQL"],
        "domains": ["distributed systems"],
        "responsibilities": ["Build backend services"],
        "qualifications": ["2+ years backend experience"],
        "nice_to_have": ["Kafka"],
        "keywords": ["Java", "Spring Boot", "backend", "distributed systems"],
    }


def plan_payload(resume: Resume, rewrite: bool = False) -> Dict[str, Any]:
    """
    A ResumePlan reply covering every entity in *resume*.

    Total coverage is a planner invariant — one entry per experience, project
    and skill category — so this is built from the resume rather than fixed.

    With ``rewrite=False`` every action is KEEP, which makes the generator issue
    *no* LLM calls at all; that is a real path worth exercising. With
    ``rewrite=True`` the summary, experiences and projects are all REWRITE, so
    all three generator calls fire.
    """
    action = "REWRITE" if rewrite else "KEEP"
    strategy = "Lead with backend platform work." if rewrite else None
    return {
        "summary_plan": {
            "action": action,
            "priority": "HIGH",
            "reasoning": "Aligns with the job.",
            "keywords_to_include": ["Java"],
        },
        "skills_plans": [
            {
                "category_id": category.id,
                "action": "KEEP",
                "priority": "MEDIUM",
                "reasoning": "Already relevant.",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": [],
            }
            for category in resume.skills
        ],
        "experience_plans": [
            {
                "experience_id": experience.id,
                "action": action,
                "priority": "HIGH",
                "reasoning": "Directly relevant.",
                "rewrite_strategy": strategy,
                "keywords_to_include": ["Java"],
                "themes_to_emphasize": ["backend"],
            }
            for experience in resume.experiences
        ],
        "project_plans": [
            {
                "project_id": project.id,
                "action": action,
                "priority": "MEDIUM",
                "reasoning": "Shows relevant work.",
                "rewrite_strategy": strategy,
                "generation_brief": None,
                "keywords_to_include": ["Java"],
                "themes_to_emphasize": ["backend"],
            }
            for project in resume.projects
        ],
    }


def experiences_payload(resume: Resume) -> Dict[str, Any]:
    """Rewritten experiences, reusing each entity's real id and role."""
    return {
        "experiences": [
            {
                "experience_id": experience.id,
                "role": experience.role,
                "technologies": list(experience.technologies),
                "domains": list(experience.domains),
                "highlights": [
                    "Built backend services in Java and Spring Boot supporting "
                    "security investigations",
                    "Designed distributed workflows processing incident data",
                ],
            }
            for experience in resume.experiences
        ]
    }


def projects_payload(resume: Resume) -> Dict[str, Any]:
    """Rewritten projects, reusing each entity's real id, name and type."""
    return {
        "projects": [
            {
                "project_id": project.id,
                "name": project.name,
                "type": project.type,
                "technologies": list(project.technologies),
                "domains": list(project.domains),
                "highlights": [
                    "Implemented a Java service handling scheduled processing",
                    "Added MySQL-backed persistence for run history",
                ],
            }
            for project in resume.projects
        ]
    }


def compression_payload(prompt: str) -> Dict[str, Any]:
    """
    Return a compression reply that keeps every protected fact.

    Built from the prompt itself: each bullet's protected facts are listed
    there, so echoing them back produces a rewrite that passes verification
    without this fixture having to know the resume's prose. A reply that
    dropped them would be rejected and the compression path would look broken
    when it was working.
    """
    payload = json.loads(prompt.split("<bullets>")[1].split("</bullets>")[0])
    return {
        "compressions": [
            {
                "bullet_id": entry["bullet_id"],
                "text": "Delivered {0}.".format(", ".join(entry["protected_facts"]))
                if entry["protected_facts"]
                else "Delivered the work item.",
            }
            for entry in payload
        ]
    }


class ScriptedProvider(LLMProvider):
    """
    Answers each stage's prompt with a canned, schema-valid reply.

    Records every prompt it saw, so a test can assert *which* calls a run made —
    an all-KEEP plan must produce zero generator calls.
    """

    def __init__(self, resume: Resume, rewrite: bool = True) -> None:
        self._resume = resume
        self._rewrite = rewrite
        self.prompts: List[str] = []
        self.stages: List[str] = []

    def generate(
        self, prompt: str, options: Optional[Dict[str, Any]] = None
    ) -> str:
        self.prompts.append(prompt)
        stage, payload = self._dispatch(prompt)
        self.stages.append(stage)
        return json.dumps(payload)

    def _dispatch(self, prompt: str):
        if ANALYSIS_MARKER in prompt:
            return "analysis", job_analysis_payload()
        if PLAN_MARKER in prompt:
            return "plan", plan_payload(self._resume, self._rewrite)
        if SUMMARY_MARKER in prompt:
            return "summary", {"summary": REWRITTEN_SUMMARY}
        if EXPERIENCES_MARKER in prompt:
            return "experiences", experiences_payload(self._resume)
        if PROJECTS_MARKER in prompt:
            return "projects", projects_payload(self._resume)
        if COMPRESSION_MARKER in prompt:
            return "compression", compression_payload(prompt)
        raise AssertionError(
            "ScriptedProvider saw a prompt it does not recognise. If a stage's "
            "prompt changed, update the markers in this file.\n\n"
            + prompt[:400]
        )
