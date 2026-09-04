"""
The Reporter: a deterministic record of what one tailoring run did.

Consumes the structured results the earlier stages already produced and writes
three artifacts. It performs no generation, no validation, no comparison of raw
Markdown, and no LLM call -- there is no provider parameter here, and the
package imports nothing from the provider layer.

It also decides nothing. Whether a skill is valid, whether a project should
exist, whether content breaches a constraint and whether the resume fits on one
page are all answered upstream; this package reports those answers. The one
piece of derivation it does perform is reconciling the plan against the
resulting resumes, and that is a set-membership join over recorded facts --
see :mod:`src.report.reconcile`.

Structured first, then rendered: :meth:`Reporter.build` produces one
:class:`~src.report.models.Report`, and the three renderers read it. None of
them re-derives anything, so the three files cannot disagree.
"""

from pathlib import Path
from typing import Dict, List, Optional

from src.parser.models import EntitySource, Resume
from src.pipeline.models import PipelineResult
from src.quality.models import QualityGateResult

from . import markdown
from .exceptions import IncompleteRunError, ReportWriteError
from .gate import gate_attempts
from .models import (
    FinalVerdict,
    Report,
    ResumeIdentity,
    ResumeShape,
    RevisionSummary,
)
from .reconcile import entity_changes, plan_entries

#: The three artifacts, named as ``tasks/018-reporter.md`` specifies. They land
#: flat in the run directory beside ``generated.md`` and
#: ``revision_trail.json`` rather than in a new directory of their own.
REPORT_FILENAME = "report.md"
CHANGES_FILENAME = "changes.md"
REPORT_JSON_FILENAME = "report.json"


def resume_identity(resume: Resume) -> ResumeIdentity:
    """Return which resume a run started from."""
    return ResumeIdentity(
        resume=resume.metadata.resume,
        template=resume.metadata.template,
        version=resume.metadata.version,
        name=resume.contact.name,
    )


def resume_shape(resume: Resume) -> ResumeShape:
    """
    Return counts and lineage for one resume, never its content.

    The generated-entity ids come from the ``EntitySource`` the Generator
    stamped. The Reporter never infers a lineage value.
    """
    return ResumeShape(
        summary_word_count=len(resume.summary.split()),
        skill_categories=len(resume.skills),
        total_skills=resume.total_skills(),
        experiences=resume.total_experiences(),
        projects=resume.total_projects(),
        education=resume.total_education(),
        total_highlights=resume.total_highlights(),
        word_count=resume.word_count(),
        generated_projects=[
            p.id for p in resume.projects if p.source is EntitySource.GENERATED
        ],
        generated_skill_categories=[
            c.id for c in resume.skills if c.source is EntitySource.GENERATED
        ],
    )


def _describe(issues) -> List[str]:
    """Render gate issues as one line each."""
    return ["{0}: {1}".format(i.code.value, i.message) for i in issues]


def final_verdict(quality: QualityGateResult) -> FinalVerdict:
    """Return the delivered resume's standing, copied from the gate."""
    return FinalVerdict(
        passed=quality.passed,
        page_count=quality.metrics.page_count,
        stage_reached=quality.stage_reached,
        total_text_lines=quality.metrics.total_text_lines,
        spill=quality.metrics.overflow_line_count,
        blocking_failures=_describe(quality.errors),
        warnings=_describe(quality.warnings),
    )


def _relative(path: Optional[str], root: Optional[Path]) -> Optional[str]:
    """
    Return a path relative to the run directory.

    Absolute paths vary between two otherwise identical runs, which would break
    the determinism the report has to guarantee. The basename is the fallback
    when the path lies outside the run directory.
    """
    if path is None:
        return None
    candidate = Path(path)
    if root is not None:
        try:
            return str(candidate.relative_to(root))
        except ValueError:
            pass
    return candidate.name


def revision_summary(revision) -> RevisionSummary:
    """Project a ``RevisionResult`` into the report, minus its heavy fields."""
    root = Path(revision.trail_path).parent if revision.trail_path else None
    return RevisionSummary(
        revised=revision.revised,
        attempts=revision.attempts,
        deterministic_steps=revision.deterministic_steps,
        compression_passes=revision.compression_passes,
        llm_calls=revision.llm_calls,
        trail=list(revision.trail),
        compression_outcomes=list(revision.compression_outcomes),
        pdf_path=_relative(revision.pdf_path, root),
        tex_path=_relative(revision.tex_path, root),
        trail_path=_relative(revision.trail_path, root),
    )


class Reporter:
    """
    Builds and renders the record of one tailoring run.

    Stateless, and it mutates nothing it is given: every list it stores is a
    fresh copy and every resume is read, never written.
    """

    def build(self, result: PipelineResult) -> Report:
        """
        Assemble the structured report for one completed run.

        Raises :class:`IncompleteRunError` when the run carries no Quality Gate
        verdict, because a report would then have to invent one.
        """
        if result.quality is None:
            raise IncompleteRunError(
                "the run carries no Quality Gate verdict, so there is nothing "
                "to report"
            )
        final = result.final_resume
        initial = (
            result.initial_quality
            if result.initial_quality is not None
            else result.quality
        )
        return Report(
            mode=result.mode,
            resume_identity=resume_identity(result.source_resume),
            target_role=result.job_analysis.role,
            job_analysis=result.job_analysis,
            plan_entries=plan_entries(result.resume_plan, result.source_resume),
            generated_shape=resume_shape(result.generated_resume),
            final_shape=resume_shape(final),
            gate_attempts=gate_attempts(initial, result.revision),
            final_verdict=final_verdict(result.quality),
            changes=entity_changes(
                result.source_resume,
                result.generated_resume,
                final,
                result.resume_plan,
                result.revision,
                list(result.planner_discarded) + list(result.generator_discarded),
            ),
            revision=(
                revision_summary(result.revision)
                if result.revision is not None
                else None
            ),
            planner_discarded=list(result.planner_discarded),
            generator_discarded=list(result.generator_discarded),
            generator_warnings=list(result.generator_warnings),
        )

    def render_report(self, report: Report) -> str:
        """Render ``report.md``, the human summary of the whole run."""
        return markdown.render_report(report)

    def render_changes(self, report: Report) -> str:
        """Render ``changes.md``, what changed in the resume and why."""
        return markdown.render_changes(report)

    def render_json(self, report: Report) -> str:
        """Render ``report.json``, the machine-readable record."""
        return report.model_dump_json(indent=2) + "\n"

    def write(self, report: Report, directory: str) -> Dict[str, str]:
        """
        Write all three artifacts into ``directory``.

        Returns the filename-to-path mapping actually written. The caller owns
        the run directory, matching every other writer in the project.
        """
        destination = Path(directory)
        payloads = {
            REPORT_FILENAME: self.render_report(report),
            CHANGES_FILENAME: self.render_changes(report),
            REPORT_JSON_FILENAME: self.render_json(report),
        }
        written = {}  # type: Dict[str, str]
        try:
            destination.mkdir(parents=True, exist_ok=True)
            for name, text in payloads.items():
                path = destination / name
                path.write_text(text, encoding="utf-8")
                written[name] = str(path)
        except OSError as error:
            raise ReportWriteError(
                "could not write the report into {0}: {1}".format(directory, error)
            )
        return written
