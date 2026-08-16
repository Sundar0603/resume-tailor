"""
Prompt templates for the Resume Planner.

Contains only prompt construction logic.
No LLM invocation, parsing, or validation here.

The planner never asks the model to write resume prose — only to decide
*what* should change and *why*, referencing every resume entity by the id
:func:`_resume_projection` assigns it. :func:`build_planning_prompt` is a
pure function of its inputs: the same resume, job analysis, and mode always
produce byte-identical prompt text.
"""

import json
from typing import Any, Dict

from src.analyzer.models import JobAnalysis
from src.parser.models import Resume

from .models import PlanningMode

_AGGRESSIVE_MODE_RULES = """\
Mode: AGGRESSIVE

In this mode you may:
- REWRITE the summary and any experience to better match the job analysis.
- REWRITE, REMOVE, or GENERATE projects to better match the job analysis.
- REWRITE, REMOVE, or GENERATE skill categories to better match the job analysis.
- Propose a GENERATE project or skill category when the job analysis reveals a clear \
gap that the existing resume does not cover.

Even in this mode, you must never invent facts. A GENERATE decision states what a new \
project or skill category should be about — the generation_brief or new_category_name \
— but never fabricates metrics, employers, dates, or responsibilities that do not \
belong to the candidate.\
"""

_STRICT_MODE_RULES = """\
Mode: STRICT

In this mode:
- GENERATE is forbidden for every section. Do not propose a new project or a new \
skill category under any circumstances.
- Every action must be one that can be carried out using only facts already present \
in the resume: KEEP or REWRITE for the summary and experience entries, and KEEP, \
REWRITE, or REMOVE for projects and skill categories.
- Nothing in your plan may require inventing metrics, employers, projects, \
responsibilities, or skills the candidate has not already listed.\
"""

#: The planning prompt. Field order in the JSON schema skeleton below is
#: load-bearing, not cosmetic.
#:
#: The skeleton asks for four different entry shapes inside one JSON object,
#: and small local models reproduce them *positionally* — the slot a field sits
#: in matters as much as its name. ``reasoning`` must therefore sit immediately
#: after ``priority`` in all four shapes, and the two shape-specific fields
#: (``new_category_name``, ``generation_brief``) must come after it.
#:
#: When ``skills_plans`` put ``new_category_name`` in that slot and listed
#: ``reasoning`` last, qwen3.6 wrote a skills-shaped GENERATE entry, then
#: carried that layout into ``project_plans`` — emitting
#: ``"new_category_name": null`` where ``reasoning`` belonged. That is two
#: validation failures at once (a required field missing and a forbidden field
#: present), and it killed the whole plan, reproducibly.
#:
#: ``tests/planner/test_determinism.py::TestSchemaFieldOrder`` pins this.
#: Reordering these fields will fail those tests by design.
_PLANNING_PROMPT_TEMPLATE = """\
You are a resume planning assistant.

Your task is to decide how the supplied resume should be reshaped to better match the \
supplied job analysis, and to explain why. You never write resume prose. You only \
decide, per section and per entity, what action should be taken.

Planning rules:
- Reference every resume entity by the id given in the resume below. Never invent an id.
- Every experience, project, and skill category in the resume must receive exactly one \
plan entry.
- A GENERATE entry has no id of its own: it proposes something new, so its id field \
must be null.
- Assign a priority to every plan entry, reflecting how much it matters for this job: \
CRITICAL, HIGH, MEDIUM, or LOW.
- Every plan entry must include a reasoning field explaining the decision in terms of \
the job analysis.

{mode_rules}

Prohibitions:
- Do NOT write summary text, bullet points, or any resume prose.
- Do NOT plan changes to education or contact information — they are immutable.
- Do NOT include scoring, an overall recommendation, or any commentary outside the \
JSON schema.

Consistency rules:
- action must be one of KEEP, REWRITE, REMOVE, or GENERATE, and must be legal for its \
section (summary and experience only support KEEP and REWRITE).
- REWRITE requires a non-empty rewrite_strategy explaining the intended change; KEEP \
and REMOVE must leave it null.
- GENERATE requires the id field to be null and requires generation_brief \
(projects) or new_category_name (skill categories) to be non-empty; every other \
action requires a non-null id and requires that field to be null.
- A GENERATE skill category must also list at least one skill in skills_to_add. \
A new category with no skills is never valid.
- A REWRITE skill category may optionally set new_category_name to rename the \
category so its heading matches the language of the job. KEEP and REMOVE must \
leave new_category_name null.
- Never list the same skill in both skills_to_add and skills_to_remove of the same \
skill category.

Skill naming rules:
- A skill is a thing a recruiter or an applicant tracking system can filter on: a \
language, framework, library, tool, database, platform, protocol, or a named, \
established technique. It is a noun, normally one or two words, never more than three.
- Write each skill the way its makers write it: "PostgreSQL", not "postgres"; \
"Kubernetes", not "k8s"; "React", not "react".
- A responsibility is not a skill. The job description describes what the role does; \
those descriptions belong in reasoning and in themes_to_emphasize, never in \
skills_to_add.
- Do not turn a phrase from the job description into a skill by capitalising it. \
These are all wrong: "Interoperability Strategies", "Optimization of Coding", \
"Application Software Development Lifecycle", "Broad Acceptance Criteria", \
"Debugging and Troubleshooting", "API Functionality", "System Maintenance", \
"Quality Assurance Processes". Each names an activity, not a technology.
- These are right: "Spring Boot", "gRPC", "Redis", "Terraform", "GraphQL", \
"Kafka", "OAuth 2.0".
- If the job description asks for something that is genuinely a skill but has no \
one-word name, prefer the concrete technology that delivers it. A job asking for \
"container orchestration experience" wants "Kubernetes" or "Docker Swarm".
- The same rules apply to a category name, which groups skills and is normally two \
to four words: "Cloud & Infrastructure", "Databases", "Testing & CI/CD".

Required JSON schema:
{{
    "summary_plan": {{
        "action": "<KEEP or REWRITE>",
        "priority": "<CRITICAL, HIGH, MEDIUM, or LOW>",
        "reasoning": "<why>",
        "keywords_to_include": ["<keyword>", ...]
    }},
    "skills_plans": [
        {{
            "category_id": "<id from the resume, or null iff action is GENERATE>",
            "action": "<KEEP, REWRITE, REMOVE, or GENERATE>",
            "priority": "<CRITICAL, HIGH, MEDIUM, or LOW>",
            "reasoning": "<why>",
            "new_category_name": "<required if action is GENERATE, optional rename if REWRITE, else null>",
            "skills_to_add": ["<skill>", ...],
            "skills_to_remove": ["<skill>", ...]
        }}
    ],
    "experience_plans": [
        {{
            "experience_id": "<id from the resume>",
            "action": "<KEEP or REWRITE>",
            "priority": "<CRITICAL, HIGH, MEDIUM, or LOW>",
            "reasoning": "<why>",
            "rewrite_strategy": "<REQUIRED when action is REWRITE: how to change it. null otherwise>",
            "keywords_to_include": ["<keyword>", ...],
            "themes_to_emphasize": ["<theme>", ...]
        }}
    ],
    "project_plans": [
        {{
            "project_id": "<id from the resume, or null iff action is GENERATE>",
            "action": "<KEEP, REWRITE, REMOVE, or GENERATE>",
            "priority": "<CRITICAL, HIGH, MEDIUM, or LOW>",
            "reasoning": "<why>",
            "rewrite_strategy": "<REQUIRED when action is REWRITE: how to change it. null otherwise>",
            "generation_brief": "<non-null only if action is GENERATE>",
            "keywords_to_include": ["<keyword>", ...],
            "themes_to_emphasize": ["<theme>", ...]
        }}
    ]
}}

Field definitions:
- summary_plan: The single plan entry for the resume summary.
- skills_plans: One entry per existing skill category, plus one entry per new category \
you propose.
- experience_plans: Exactly one entry per experience listed in the resume.
- project_plans: One entry per existing project, plus one entry per new project you \
propose.
- keywords_to_include / themes_to_emphasize: Free-text terms drawn from the job \
analysis, not resume prose.

Resume:
<resume>
{resume}
</resume>

Job analysis:
<job_analysis>
{job_analysis}
</job_analysis>

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""


def build_planning_prompt(
    resume: Resume,
    job_analysis: JobAnalysis,
    mode: PlanningMode = PlanningMode.AGGRESSIVE,
) -> str:
    """
    Build the planning prompt for the supplied resume, job analysis, and mode.

    Parameters
    ----------
    resume : Resume
        The parsed resume to plan against.
    job_analysis : JobAnalysis
        The structured job analysis to plan toward.
    mode : PlanningMode
        Controls how aggressively the planner may reshape the resume.

    Returns
    -------
    str
        The fully constructed prompt ready to be sent to the LLM provider.
        Byte-identical for a given resume, job analysis, and mode.
    """
    mode_rules = (
        _AGGRESSIVE_MODE_RULES if mode == PlanningMode.AGGRESSIVE else _STRICT_MODE_RULES
    )
    resume_json = json.dumps(
        _resume_projection(resume), indent=2, ensure_ascii=False
    )
    return _PLANNING_PROMPT_TEMPLATE.format(
        mode_rules=mode_rules,
        resume=resume_json,
        job_analysis=job_analysis.model_dump_json(indent=2),
    )


def _resume_projection(resume: Resume) -> Dict[str, Any]:
    """
    Project a Resume down to only what the planner is allowed to see.

    Deliberately excluded: ``contact`` and ``metadata`` (PII, irrelevant to
    planning), ``education`` (immutable — sending it would invite the model
    to plan against it), and per-entity ``source``, ``employment_type``,
    ``location``, ``repository``. A smaller prompt runs faster on local
    models and keeps personal data off the wire entirely.
    """
    return {
        "summary": resume.summary,
        "skills": [
            {
                "id": category.id,
                "category": category.category,
                "skills": list(category.skills),
            }
            for category in resume.skills
        ],
        "experiences": [
            {
                "id": experience.id,
                "company": experience.company,
                "role": experience.role,
                "duration": experience.duration,
                "technologies": list(experience.technologies),
                "domains": list(experience.domains),
                "highlights": list(experience.highlights),
            }
            for experience in resume.experiences
        ],
        "projects": [
            {
                "id": project.id,
                "name": project.name,
                "type": project.type,
                "technologies": list(project.technologies),
                "highlights": list(project.highlights),
            }
            for project in resume.projects
        ],
    }
