"""
Factories for the Reporter suite.

House style: plain functions returning deep copies, not pytest fixtures and not
files. The Reporter needs no provider, no compiler and no TeX distribution, so
every test here runs everywhere -- unlike ``tests/pipeline`` and
``tests/quality``, which skip without pdflatex.

Resume, plan and gate-verdict builders are **imported from the packages that
already own them** rather than copied. ``tests`` is a package, so this works,
and a second copy of ``make_resume`` would be one more thing to keep in step
with the models.
"""

import copy
from typing import Any, Dict, List, Optional, Sequence

from tests.generator.conftest import make_plan
from tests.planner.conftest import make_job_analysis
from tests.revision.conftest import failing_result, make_resume, passing_result

from src.parser.models import EntitySource, Project, Resume, SkillCategory
from src.pipeline.models import PipelineResult
from src.planner.models import PlanningMode
from src.quality.models import QualityGateResult
from src.revision.models import (
    CompressionOutcome,
    EntityKind,
    RevisionAction,
    RevisionReason,
    RevisionResult,
    RevisionStep,
)

__all__ = [
    "make_resume",
    "make_plan",
    "make_job_analysis",
    "passing_result",
    "failing_result",
    "make_source_resume",
    "generated_project",
    "generated_category",
    "removal_step",
    "compression_step",
    "make_revision_result",
    "make_pipeline_result",
]

#: Two skill categories, matching the ids ``make_plan`` plans for.
_SKILL_SIZES = (4, 4)


def make_source_resume(**overrides: Any) -> Resume:
    """Return a resume whose entity ids line up with :func:`make_plan`."""
    overrides.setdefault("skill_sizes", _SKILL_SIZES)
    return make_resume(**overrides)


def generated_project(
    project_id: str = "proj_003", name: str = "Threat Feed Aggregator"
) -> Project:
    """Return a project carrying the lineage the Generator would stamp."""
    return Project(
        id=project_id,
        source=EntitySource.GENERATED,
        name=name,
        type="Personal",
        technologies=["Python"],
        domains=["Security Operations"],
        highlights=["Ingested twelve threat feeds.", "Cut triage time by 40%."],
    )


def generated_category(
    category_id: str = "skill_003", category: str = "Security Tooling"
) -> SkillCategory:
    """Return a skill category carrying generated lineage."""
    return SkillCategory(
        id=category_id,
        source=EntitySource.GENERATED,
        category=category,
        skills=["Splunk", "Suricata"],
    )


def removal_step(
    attempt: int,
    action: RevisionAction,
    entity_id: str,
    entity_kind: EntityKind,
    page_count: int,
    spill: int,
    passed: bool,
    detail: str = "a bullet",
) -> RevisionStep:
    """Return one deterministic removal as the engine would record it."""
    return RevisionStep(
        attempt=attempt,
        action=action,
        reason=RevisionReason.PAGE_OVERFLOW,
        entity_id=entity_id,
        entity_kind=entity_kind,
        detail=detail,
        page_count=page_count,
        spill=spill,
        passed=passed,
    )


def compression_step(
    attempt: int,
    bullet_ids: Sequence[str],
    page_count: int,
    spill: int,
    passed: bool,
) -> RevisionStep:
    """Return one consolidated compression pass as the engine records it."""
    return RevisionStep(
        attempt=attempt,
        action=RevisionAction.COMPRESS_BULLETS,
        reason=RevisionReason.SHORTFALL_REMAINS,
        bullet_ids=list(bullet_ids),
        shortfall_before=spill + 1,
        detail="{0} of {0} compressions accepted".format(len(bullet_ids)),
        page_count=page_count,
        spill=spill,
        passed=passed,
    )


def make_revision_result(
    resume: Resume,
    trail: Optional[List[RevisionStep]] = None,
    gate_results: Optional[List[QualityGateResult]] = None,
    quality: Optional[QualityGateResult] = None,
    compression_outcomes: Optional[List[CompressionOutcome]] = None,
    llm_calls: int = 0,
    compression_passes: int = 0,
    root: str = "/runs/example",
) -> RevisionResult:
    """
    Return a revision result whose counts agree with its trail.

    ``root`` is deliberately a fixed fake path: the paths on a real result are
    absolute and vary per run, which is exactly what the determinism test
    checks the Reporter strips.
    """
    steps = list(trail) if trail is not None else []
    results = list(gate_results) if gate_results is not None else []
    return RevisionResult(
        resume=copy.deepcopy(resume),
        quality=quality if quality is not None else passing_result(),
        revised=bool(steps),
        attempts=len(results),
        deterministic_steps=sum(
            1 for s in steps if s.action is not RevisionAction.COMPRESS_BULLETS
        ),
        compression_passes=compression_passes,
        llm_calls=llm_calls,
        trail=steps,
        compression_outcomes=list(compression_outcomes or []),
        gate_results=results,
        pdf_path="{0}/final/resume.pdf".format(root),
        tex_path="{0}/final/resume.tex".format(root),
        trail_path="{0}/revision_trail.json".format(root),
    )


def make_pipeline_result(**overrides: Any) -> PipelineResult:
    """
    Return a complete run, all-KEEP and passing on the first compile.

    All-KEEP and passing is the useful baseline: a test that overrides one
    piece is then exercising exactly that piece.
    """
    source = overrides.pop("source_resume", None)
    if source is None:
        source = make_source_resume()
    generated = overrides.pop("generated_resume", None)
    if generated is None:
        generated = copy.deepcopy(source)
    defaults = {
        "mode": PlanningMode.STRICT,
        "source_resume": source,
        "job_analysis": make_job_analysis(),
        "resume_plan": make_plan(),
        "generated_resume": generated,
        "markdown": "# generated\n",
        "latex": "\\documentclass{article}\n",
        "quality": passing_result(),
        "initial_quality": passing_result(),
    }  # type: Dict[str, Any]
    defaults.update(overrides)
    return PipelineResult(**defaults)
