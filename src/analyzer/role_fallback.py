"""
Fallback job title resolution.

A job description pasted from a careers page routinely carries no title:
the heading holds it, and the copied body starts at "Job Requirements".
The extraction prompt forbids inventing a role, so the model correctly
returns null — correct, and useless, because every downstream stage needs
a target role to tailor against.

This module resolves that case with a second, deliberately narrow call.
The model is not asked to write a title; it is asked to pick one from a
closed list. A closed list keeps the invention bounded (the model cannot
conjure "Ninja Rockstar Engineer" out of a requirements block), keeps the
answer checkable (an off-list reply is rejected rather than trusted), and
keeps the result reproducible for a given job description.

A resolved title is always marked: :attr:`JobAnalysis.role_inferred` is
True whenever the role came from here rather than from the job description,
so a report never presents a guessed title as a stated one.

Seniority is deliberately absent from every entry. It is a separate field
on JobAnalysis, extracted from the body text where the years-of-experience
line usually survives the copy/paste that lost the heading. Baking it into
the title would produce "Senior Senior Software Engineer" downstream.
"""

from typing import Optional

from ._json_extract import extract_json_object
from .exceptions import AnalyzerError, MissingJobRole
from .provider import LLMProvider
from .sampling import deterministic_options

import json

#: The closed set of fallback titles, in the order shown to the model.
#:
#: Kept small on purpose. The list exists to name what a job description is
#: obviously about, not to classify it precisely — a near-miss title that
#: the resume then tailors toward is far better than a hard failure, and a
#: longer list mostly adds ways for the model to split hairs. Add an entry
#: only when a real job description had no reasonable home among these.
FALLBACK_ROLES = (
    "Software Engineer",
    "Software Developer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Platform Engineer",
    "Security Engineer",
    "Data Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "QA Engineer",
)

_ROLE_FALLBACK_PROMPT_TEMPLATE = """\
You are a job title classifier.

The job description below does not state its job title. Your task is to \
choose the single title that best fits the work it describes.

Rules:
- Choose exactly one title from the allowed list. Copy it verbatim.
- Do not invent a title. Do not combine two titles.
- Do not add a seniority level, a team name, or a company name.
- If several fit, choose the most general one.

Allowed titles:
{allowed}

Return ONLY this JSON object, with no explanation and no markdown:

{{"role": "<one title from the allowed list>"}}

Job description:
<job_description>
{job_description}
</job_description>
"""


def build_role_fallback_prompt(job_description: str) -> str:
    """
    Build the fallback classification prompt.

    Byte-identical for a given job description, like every other analyzer
    prompt: a prompt that varies defeats the pinned sampling parameters.
    """
    allowed = "\n".join("- {0}".format(role) for role in FALLBACK_ROLES)
    return _ROLE_FALLBACK_PROMPT_TEMPLATE.format(
        allowed=allowed,
        job_description=job_description,
    )


def resolve_role(provider: LLMProvider, job_description: str) -> str:
    """
    Choose a fallback title for a job description that states none.

    Parameters
    ----------
    provider : LLMProvider
        The same provider the analysis ran on, so a single run never mixes
        models between the analysis and the title it is filed under.
    job_description : str
        The raw job description text.

    Returns
    -------
    str
        One entry of :data:`FALLBACK_ROLES`, verbatim.

    Raises
    ------
    MissingJobRole
        If no title can be resolved. The caller's original failure is the
        right one to report: the job description has no title in it, and
        now we also know it does not resemble anything on the list.
    """
    try:
        response = provider.generate(
            build_role_fallback_prompt(job_description),
            options=deterministic_options(),
        )
    except AnalyzerError:
        raise
    except Exception as exc:
        raise MissingJobRole(
            "The job description does not state a job title, and choosing "
            "one failed: {0}".format(exc)
        ) from exc

    role = _match(_extract_role(response))
    if role is None:
        raise MissingJobRole(
            "The job description does not state a job title, and it does "
            "not match any of the known fallback titles."
        )
    return role


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_role(response: Optional[str]) -> str:
    """
    Pull the role string out of the model response.

    Tolerant by design: the answer is one field, and a model that returns
    a bare title instead of the requested object has still answered the
    question. Only the empty response is a real failure, and that surfaces
    as an off-list reply in :func:`_match`.
    """
    if not response or not response.strip():
        return ""

    text = response.strip()
    try:
        parsed = json.loads(extract_json_object(text))
    except json.JSONDecodeError:
        return text

    if isinstance(parsed, dict):
        value = parsed.get("role")
        return value if isinstance(value, str) else ""
    return text


def _match(candidate: str) -> Optional[str]:
    """
    Map a model reply onto the closed list, or return None.

    Three passes, narrowing in tolerance: exact, case-insensitive, then
    containment either way — which catches "Senior Software Engineer" and
    "Engineer (Software)" alike, both of which mean the list entry. An
    answer that survives all three is genuinely off-list, and the caller
    treats that as a failure rather than guessing.
    """
    if not candidate:
        return None

    text = candidate.strip().strip('"').strip()
    if not text:
        return None

    for role in FALLBACK_ROLES:
        if text == role:
            return role

    folded = text.casefold()
    for role in FALLBACK_ROLES:
        if folded == role.casefold():
            return role

    for role in FALLBACK_ROLES:
        lowered = role.casefold()
        if lowered in folded or folded in lowered:
            return role

    return None
