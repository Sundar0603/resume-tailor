"""
Prompt templates for the Resume Generator.

Contains only prompt construction logic. No LLM invocation, parsing, or
validation here.

Where the Planner decides *what* changes, the Generator writes *the words*.
There are three prompts — summary, experiences, projects — rather than one
whole-resume prompt: each stays small enough for a local model to handle, and
a failure in one section does not destroy the others. Skills have no prompt at
all; the Planner already emits literal category names and skill strings, so the
Generator applies them in pure Python.

Every builder is a pure function of its inputs: the same resume, job analysis,
plan and mode always produce byte-identical prompt text.
"""

import json
from typing import Any, Dict, List, Optional

from src.analyzer.models import JobAnalysis
from src.parser.models import Resume

from ..planner.models import (
    ExperiencePlan,
    PlanAction,
    PlanningMode,
    ProjectPlan,
    ResumePlan,
)

#: Budgets the ResumeValidator checks. Stated in the prompts so the model aims
#: inside them rather than being corrected afterwards.
SUMMARY_MIN_WORDS = 20
SUMMARY_MAX_WORDS = 120
MAX_EXPERIENCE_HIGHLIGHTS = 8
MAX_PROJECT_HIGHLIGHTS = 6

_AGGRESSIVE_MODE_RULES = """\
Mode: AGGRESSIVE

In this mode you may:
- Add technologies, skills, and keywords drawn from the job analysis.
- Add quantified metrics and achievements that plausibly fit the work described.
- Write new projects from a generation brief.
- Reframe existing experience toward the target role.
- Retitle a role to match the target job — "Software Engineer" may become \
"Backend Engineer" when the work supports that reading.

Give every experience and every project at least one quantified outcome. A bullet \
with a number in it is the one a reviewer believes and remembers, and a section \
without any reads as unmeasured work.

A quantified outcome must be believable. That means:
- It follows from the work the bullet actually describes. Query tuning yields a \
latency or throughput figure; it does not yield a revenue figure.
- It is round and modest, the way a real engineer recalls it: "cut query time by \
around 40%", not "cut query time by 43.7%".
- It stays inside the ordinary range for the thing being measured. Latency and cost \
reductions live between 10% and 80%; uptime lives between 99% and 99.99%; a rewrite \
does not make something 500% faster.
- It never invents a fact about the employer. Team size, headcount, revenue, customer \
counts and funding are checkable, and a reviewer who checks one and finds it wrong \
stops believing the rest.
- Where the source resume already gives a number that fits, reuse that number rather \
than inventing a second one.

Even in this mode you must not:
- Change the employer, the dates, the employment type, or the location of any \
experience.
- Inflate seniority. A role may be retitled sideways, never upward: never turn \
"Engineer" into "Senior Engineer", "Lead", "Staff", "Principal", "Manager", or \
"Head of" anything.
- Claim a degree, certification, or employer the candidate does not have.\
"""

_STRICT_MODE_RULES = """\
Mode: STRICT

In this mode every word you write must be supported by the source resume. You may \
rewrite, reorder, sharpen, and re-emphasise, but you may not add facts.

You must not:
- Name any technology, tool, framework, or skill that does not already appear \
somewhere in the source resume.
- Introduce any number, percentage, or quantity that does not already appear in the \
source resume. If a bullet has no metric, it stays without one.
- Add achievements, responsibilities, or outcomes that are not already stated.
- Change the role title. Reproduce it exactly as given.

Rewriting "Built the payment service" into "Designed and shipped the payment service, \
owning it end to end" is good work. Rewriting it into "Built the payment service, \
cutting latency 40%" is a fabrication, because the 40% appears nowhere in the source.\
"""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

_SUMMARY_PROMPT_TEMPLATE = """\
You are a resume writing assistant. You write one section at a time.

Your task: rewrite the professional summary so it speaks directly to the target job, \
following the plan below.

{mode_rules}

Writing rules:
- Write {min_words} to {max_words} words. This is a hard budget.
- Write in the third person with no pronouns, the way resume summaries are written. \
Do not start with "I" or the candidate's name.
- Lead with what the candidate is, then what they have done, then what they bring to \
this role.
- Keep the specifics the current summary already has: the employer, the years of \
experience, and the named technologies. Those are what make the rest believable. \
Replacing "Backend Software Engineer with 2 years at Zoho building platforms in Java, \
Spring Boot and Redis" with "Application Software Development professional" trades a \
fact for a job title and gains nothing — the job's own words belong *around* those \
specifics, not instead of them.
- Work the listed keywords in naturally. A keyword that cannot be used honestly is \
left out.
- Write normal sentence case. Do not capitalise a keyword mid-sentence to make it \
stand out: write "code quality assurance", not "Code Quality assurance"; "production \
support", not "production Support". Only proper nouns are capitalised — product and \
technology names like Java, Spring Boot, AWS.
- No headings, no bullet points, no markdown.

Plan for the summary:
<plan>
{summary_plan}
</plan>

Current summary:
<summary>
{summary}
</summary>

Resume:
<resume>
{resume}
</resume>

Job analysis:
<job_analysis>
{job_analysis}
</job_analysis>

Required JSON schema:
{{
    "summary": "<the rewritten summary>"
}}

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""

# ---------------------------------------------------------------------------
# Experiences
# ---------------------------------------------------------------------------

#: Field order in the schema skeletons below is load-bearing, not cosmetic.
#:
#: Small local models reproduce a repeated JSON shape *positionally* — the slot
#: a field sits in matters as much as its name. The experience and project
#: shapes share four fields (``name``/``role``, ``technologies``, ``domains``,
#: ``highlights``), and those must sit in the same order in both, with the
#: id field first and ``highlights`` last.
#:
#: This is the same failure the Planner hit: when two similar shapes disagreed
#: on field order, qwen3.6 carried one shape's layout into the other and
#: emitted a field where a different one belonged, killing the whole response.
#: See ``src/planner/prompts.py`` and
#: ``tests/generator/test_determinism.py::TestSchemaFieldOrder``, which pins
#: this. Reordering these fields will fail those tests by design.
_EXPERIENCE_PROMPT_TEMPLATE = """\
You are a resume writing assistant. You write one section at a time.

Your task: rewrite the work experience entries listed in the plan below, so they speak \
directly to the target job.

{mode_rules}

Writing rules:
- Rewrite only the experiences listed in the plan. Return one entry for each, keyed by \
the experience_id given.
- Write at most {max_highlights} highlights per experience. Fewer, sharper bullets beat \
more, weaker ones. Do not pad to the limit: if the source has four highlights worth \
keeping, return four.
- Order the highlights strongest first. A later stage trims this resume from the \
bottom to fit one page, so the last bullet in your list must be the one you would give \
up first. Lead with the bullet that best matches the job and carries the most concrete \
outcome.
- Start every highlight with a strong past-tense verb. No pronouns, no trailing period \
inconsistency — be consistent.
- Each highlight states what was done and why it mattered. Avoid "Responsible for".
- Write normal sentence case. Do not capitalise a keyword mid-sentence to make it \
stand out: write "software testing", not "Software Testing". Only proper nouns are \
capitalised — product and technology names like Java, Spring Boot, AWS.
- technologies lists concrete tools and languages. domains lists problem areas, such \
as payments, observability, or distributed systems.
- Work the listed keywords and themes in naturally. Anything that cannot be used \
honestly is left out.
- Reproduce the company, dates, employment type, and location exactly. They are \
immutable and are not part of your output.
- No markdown, no bullet characters. Each highlight is a plain sentence.

Plan for the experiences:
<plan>
{experience_plans}
</plan>

Resume:
<resume>
{resume}
</resume>

Job analysis:
<job_analysis>
{job_analysis}
</job_analysis>

Required JSON schema:
{{
    "experiences": [
        {{
            "experience_id": "<the id given in the plan>",
            "role": "<the role title>",
            "technologies": ["<technology>", ...],
            "domains": ["<domain>", ...],
            "highlights": ["<highlight>", ...]
        }}
    ]
}}

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""

# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

_PROJECT_PROMPT_TEMPLATE = """\
You are a resume writing assistant. You write one section at a time.

Your task: write the project entries listed in the plan below, so they speak directly \
to the target job.

{mode_rules}

Writing rules:
- Write only the projects listed in the plan. Return one entry for each.
- A plan entry with a project_id rewrites that existing project. Return the same \
project_id.
- A plan entry with a null project_id and a generation_brief is a new project. Return \
project_id as null and invent a fitting name and type from the brief.
- Write at most {max_highlights} highlights per project. Do not pad to the limit.
- Order the highlights strongest first. A later stage trims this resume from the \
bottom to fit one page, so the last bullet in your list must be the one you would give \
up first.
- Start every highlight with a strong past-tense verb. Each states what was built and \
what it achieved.
- type is a short category such as "Personal", "Open Source", "Academic", or \
"Professional".
- technologies lists concrete tools and languages. domains lists problem areas.
- Work the listed keywords and themes in naturally.
- No markdown, no bullet characters. Each highlight is a plain sentence.

Plan for the projects:
<plan>
{project_plans}
</plan>

Resume:
<resume>
{resume}
</resume>

Job analysis:
<job_analysis>
{job_analysis}
</job_analysis>

Required JSON schema:
{{
    "projects": [
        {{
            "project_id": "<the id given in the plan, or null for a new project>",
            "name": "<the project name>",
            "type": "<short category>",
            "technologies": ["<technology>", ...],
            "domains": ["<domain>", ...],
            "highlights": ["<highlight>", ...]
        }}
    ]
}}

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _mode_rules(mode: PlanningMode) -> str:
    """Return the mode rule block for the given tailoring mode."""
    if mode == PlanningMode.AGGRESSIVE:
        return _AGGRESSIVE_MODE_RULES
    return _STRICT_MODE_RULES


def _dumps(payload: Any) -> str:
    """Serialise a projection to stable, readable JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_summary_prompt(
    resume: Resume,
    job_analysis: JobAnalysis,
    plan: ResumePlan,
    mode: PlanningMode,
) -> str:
    """
    Build the summary generation prompt.

    Byte-identical for a given resume, job analysis, plan and mode.
    """
    return _SUMMARY_PROMPT_TEMPLATE.format(
        mode_rules=_mode_rules(mode),
        min_words=SUMMARY_MIN_WORDS,
        max_words=SUMMARY_MAX_WORDS,
        summary_plan=_dumps(_summary_plan_projection(plan)),
        summary=resume.summary,
        resume=_dumps(_resume_projection(resume)),
        job_analysis=job_analysis.model_dump_json(indent=2),
    )


def build_experiences_prompt(
    resume: Resume,
    job_analysis: JobAnalysis,
    plan: ResumePlan,
    mode: PlanningMode,
) -> str:
    """
    Build the experience generation prompt.

    Only experiences the plan marked REWRITE are included; KEEP entries are
    copied in Python and never reach the model.
    """
    rewrites = [p for p in plan.experience_plans if p.action == PlanAction.REWRITE]
    return _EXPERIENCE_PROMPT_TEMPLATE.format(
        mode_rules=_mode_rules(mode),
        max_highlights=MAX_EXPERIENCE_HIGHLIGHTS,
        experience_plans=_dumps(
            [_experience_plan_projection(p, resume) for p in rewrites]
        ),
        resume=_dumps(_resume_projection(resume)),
        job_analysis=job_analysis.model_dump_json(indent=2),
    )


def build_projects_prompt(
    resume: Resume,
    job_analysis: JobAnalysis,
    plan: ResumePlan,
    mode: PlanningMode,
) -> str:
    """
    Build the project generation prompt.

    Only projects the plan marked REWRITE or GENERATE are included. KEEP
    entries are copied and REMOVE entries dropped, both in Python.
    """
    wanted = [
        p
        for p in plan.project_plans
        if p.action in (PlanAction.REWRITE, PlanAction.GENERATE)
    ]
    return _PROJECT_PROMPT_TEMPLATE.format(
        mode_rules=_mode_rules(mode),
        max_highlights=MAX_PROJECT_HIGHLIGHTS,
        project_plans=_dumps([_project_plan_projection(p, resume) for p in wanted]),
        resume=_dumps(_resume_projection(resume)),
        job_analysis=job_analysis.model_dump_json(indent=2),
    )


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------
#
# Plans are projected by hand rather than with ``model_dump_json()``. Two
# reasons: ``SectionPriority`` is an ``IntEnum``, so a dump renders MEDIUM as
# ``3``, which tells a language model nothing; and a plan entry carries fields
# the generator has no business showing the model, such as the action itself.


def _priority_name(plan_entry: Any) -> str:
    """Return the readable priority name, not the IntEnum's integer value."""
    return plan_entry.priority.name


def _summary_plan_projection(plan: ResumePlan) -> Dict[str, Any]:
    """Project the summary plan into the fields the writer needs."""
    summary_plan = plan.summary_plan
    return {
        "priority": _priority_name(summary_plan),
        "reasoning": summary_plan.reasoning,
        "keywords_to_include": list(summary_plan.keywords_to_include),
    }


def _experience_plan_projection(
    plan_entry: ExperiencePlan, resume: Resume
) -> Dict[str, Any]:
    """Project one experience plan entry, resolved against the resume."""
    return {
        "experience_id": plan_entry.experience_id,
        "priority": _priority_name(plan_entry),
        "reasoning": plan_entry.reasoning,
        "rewrite_strategy": plan_entry.rewrite_strategy,
        "keywords_to_include": list(plan_entry.keywords_to_include),
        "themes_to_emphasize": list(plan_entry.themes_to_emphasize),
        "current_role": _experience_role(resume, plan_entry.experience_id),
    }


def _project_plan_projection(
    plan_entry: ProjectPlan, resume: Resume
) -> Dict[str, Any]:
    """Project one project plan entry, resolved against the resume."""
    return {
        "project_id": plan_entry.project_id,
        "priority": _priority_name(plan_entry),
        "reasoning": plan_entry.reasoning,
        "rewrite_strategy": plan_entry.rewrite_strategy,
        "generation_brief": plan_entry.generation_brief,
        "keywords_to_include": list(plan_entry.keywords_to_include),
        "themes_to_emphasize": list(plan_entry.themes_to_emphasize),
        "current_name": _project_name(resume, plan_entry.project_id),
    }


def _experience_role(resume: Resume, experience_id: str) -> Optional[str]:
    """Return the current role for an experience id, or None if unknown."""
    for experience in resume.experiences:
        if experience.id == experience_id:
            return experience.role
    return None


def _project_name(resume: Resume, project_id: Optional[str]) -> Optional[str]:
    """Return the current name for a project id, or None for a new project."""
    if project_id is None:
        return None
    for project in resume.projects:
        if project.id == project_id:
            return project.name
    return None


def _resume_projection(resume: Resume) -> Dict[str, Any]:
    """
    Project a Resume down to only what a section writer is allowed to see.

    Deliberately excluded, matching the Planner's projection: ``contact`` and
    ``metadata`` (PII, irrelevant to writing), ``education`` (immutable), and
    per-entity ``source`` and ``repository``. ``company`` and ``duration`` are
    included because a writer needs the context, even though it may not change
    them. A smaller prompt runs faster on local models and keeps personal data
    off the wire.
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
                "domains": list(project.domains),
                "highlights": list(project.highlights),
            }
            for project in resume.projects
        ],
    }


def experience_ids_in_prompt(plan: ResumePlan) -> List[str]:
    """Return the experience ids the experience prompt asks the model to write."""
    return [
        p.experience_id
        for p in plan.experience_plans
        if p.action == PlanAction.REWRITE
    ]
