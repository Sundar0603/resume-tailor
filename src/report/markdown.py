"""
Rendering a built :class:`~src.report.models.Report` as Markdown.

Two documents, one structured source. Nothing here derives a fact: every value
is read off the report, so ``report.md``, ``changes.md`` and ``report.json``
cannot disagree with each other or with the pipeline.

Same shape as ``src/renderer/latex_renderer.py`` -- ``List[str]`` builders,
banner-comment sections, no file I/O. Writing is the Reporter's job, and the
run directory is the caller's.
"""

from typing import List, Sequence

from src.parser.models import EntitySource
from src.quality.models import ResumeSection

from .models import (
    CheckOutcome,
    CheckStatus,
    EffectiveAction,
    EntityChange,
    GateAttempt,
    PlanEntry,
    Report,
    SECTION_LABELS,
    CHANGE_SECTION_ORDER,
)

#: Rendered when a list the report expected to carry values is empty.
_NONE = "_none_"


def _document(lines: Sequence[str]) -> str:
    """Join rendered lines into a document with exactly one trailing newline."""
    return "\n".join(lines).rstrip("\n") + "\n"


def _terms(label: str, values: Sequence[str]) -> str:
    """Render a named list of terms on one line."""
    return "- {0}: {1}".format(label, ", ".join(values) if values else _NONE)


def _sub_bullets(items: Sequence[str], indent: str = "  ") -> List[str]:
    """Render an indented bullet list."""
    return ["{0}- {1}".format(indent, item) for item in items]


# ----------------------------------------------------------------------
# report.md
# ----------------------------------------------------------------------


def _run_information(report: Report) -> List[str]:
    """Render the run's identity."""
    identity = report.resume_identity
    return [
        "## Run information",
        "",
        "- Mode: **{0}**".format(report.mode.value),
        "- Source resume: `{0}` (template `{1}`, version `{2}`)".format(
            identity.resume, identity.template, identity.version
        ),
        "- Candidate: {0}".format(identity.name),
        "- Target role: **{0}**".format(report.target_role or "not stated"),
        "",
    ]


def _job_analysis(report: Report) -> List[str]:
    """
    Render the job analysis already produced by the Analyzer.

    No LLM call: this is the stored ``JobAnalysis``, reformatted.
    """
    analysis = report.job_analysis
    lines = [
        "## Job analysis",
        "",
        "- Company: {0}".format(analysis.company or _NONE),
        "- Seniority: {0}".format(analysis.seniority or _NONE),
        _terms("Required skills", analysis.required_skills),
        _terms("Preferred skills", analysis.preferred_skills),
        _terms("Technologies", analysis.technologies),
        _terms("Domains", analysis.domains),
        _terms("Important keywords", analysis.keywords),
        "",
        "### Key responsibilities",
        "",
    ]
    lines.extend(
        _sub_bullets(analysis.responsibilities, indent="")
        if analysis.responsibilities
        else [_NONE]
    )
    lines.append("")
    return lines


def _plan_entry_line(entry: PlanEntry) -> str:
    """
    Render one planner decision.

    Only two kinds of entry lack a runtime id, and they are not the same
    thing: the summary has none because it is a plain string on the resume,
    and a ``GENERATE`` entry has none because the entity it asks for does not
    exist yet.
    """
    if entry.entity_id is not None:
        identifier = "`{0}` ".format(entry.entity_id)
    elif entry.section is ResumeSection.SUMMARY:
        identifier = ""
    else:
        identifier = "`(new)` "
    return "- {0}**{1}** (priority {2}) — {3}".format(
        identifier,
        entry.action.value,
        entry.priority,
        entry.label,
    )


def _resume_plan(report: Report) -> List[str]:
    """Render what the Planner decided, grouped by section."""
    lines = ["## Resume plan", ""]
    for section in CHANGE_SECTION_ORDER:
        entries = [e for e in report.plan_entries if e.section is section]
        if not entries:
            continue
        lines.append("### {0}".format(SECTION_LABELS[section]))
        lines.append("")
        for entry in entries:
            lines.append(_plan_entry_line(entry))
            if entry.reasoning:
                lines.append("  - reason: {0}".format(entry.reasoning))
            if entry.generation_brief:
                lines.append("  - brief: {0}".format(entry.generation_brief))
            if entry.rewrite_strategy:
                lines.append("  - strategy: {0}".format(entry.rewrite_strategy))
        lines.append("")
    return lines


def _check_line(check: CheckOutcome) -> str:
    """
    Render one Quality Gate check.

    ``NOT_REACHED`` is rendered as such rather than as a pass: on a compilation
    failure the geometry metrics are zero because no PDF was ever opened.
    """
    if check.status is CheckStatus.NOT_REACHED:
        return "- {0}: NOT REACHED".format(check.name)
    body = check.status.value
    if check.count is not None:
        body = "{0} ({1})".format(body, check.count)
    if check.status is CheckStatus.WARNING:
        body = "{0} — non-blocking".format(body)
    if check.status is not CheckStatus.PASS and check.detail:
        body = "{0} — {1}".format(body, check.detail)
    return "- {0}: {1}".format(check.name, body)


def _attempt_block(attempt: GateAttempt) -> List[str]:
    """Render one attempt's verdict and every check behind it."""
    lines = [
        "### Attempt {0} — {1}".format(attempt.attempt, attempt.label),
        "",
        "- Verdict: **{0}** ({1}, {2} page(s), {3} line(s) overflowing)".format(
            "PASS" if attempt.passed else "FAIL",
            attempt.stage_reached.value,
            attempt.page_count,
            attempt.spill,
        ),
    ]
    lines.extend(_check_line(check) for check in attempt.checks)
    lines.append("")
    return lines


def _quality_gate(report: Report) -> List[str]:
    """Render the gate's progression across every attempt."""
    lines = ["## Quality gate", ""]
    if len(report.gate_attempts) == 1:
        lines.append("One attempt: the first compile was judged and not revised.")
        lines.append("")
    for attempt in report.gate_attempts:
        lines.extend(_attempt_block(attempt))
    return lines


def _revision(report: Report) -> List[str]:
    """Render what the Revision Engine did, from its own trail."""
    revision = report.revision
    if revision is None:
        return [
            "## Revision",
            "",
            "Not run: the resume was accepted on its first compile.",
            "",
        ]
    lines = [
        "## Revision",
        "",
        "- Attempts: **{0}**".format(revision.attempts),
        "- Deterministic removals: **{0}**".format(revision.deterministic_steps),
        "- Compression passes: **{0}** (LLM calls: {1})".format(
            revision.compression_passes, revision.llm_calls
        ),
        "",
        "| attempt | action | entity | pages | spill |",
        "|---|---|---|---|---|",
    ]
    for step in revision.trail:
        lines.append(
            "| {0} | `{1}` | `{2}` | {3} | {4} |".format(
                step.attempt,
                step.action.value,
                step.entity_id or "-",
                step.page_count if step.page_count is not None else "-",
                step.spill if step.spill is not None else "-",
            )
        )
    lines.append("")
    lines.extend(_compression_outcomes(revision.compression_outcomes))
    return lines


def _compression_outcomes(outcomes: Sequence) -> List[str]:
    """
    Render each bullet the compression pass tried to shorten.

    Rejections matter as much as acceptances: a rejected compression means the
    model dropped a protected fact, and the trail's one-line "n of m accepted"
    does not say which bullet or why.
    """
    if not outcomes:
        return []
    lines = ["### Compression outcomes", ""]
    for outcome in outcomes:
        if outcome.accepted:
            lines.append("- `{0}` accepted".format(outcome.bullet_id))
        else:
            lines.append(
                "- `{0}` rejected — {1}".format(
                    outcome.bullet_id, outcome.rejection or "no reason recorded"
                )
            )
    lines.append("")
    return lines


def _final_result(report: Report) -> List[str]:
    """Render the delivered resume's standing."""
    verdict = report.final_verdict
    shape = report.final_shape
    lines = [
        "## Final result",
        "",
        "- Quality Gate: **{0}**".format("PASSED" if verdict.passed else "FAILED"),
        "- Pages: **{0}**".format(verdict.page_count),
        "- Text lines: {0} ({1} overflowing)".format(
            verdict.total_text_lines, verdict.spill
        ),
        "- Stage reached: {0}".format(verdict.stage_reached.value),
        "- Delivered resume: {0} skill(s) in {1} category/ies, {2} experience(s), "
        "{3} project(s), {4} highlight(s)".format(
            shape.total_skills,
            shape.skill_categories,
            shape.experiences,
            shape.projects,
            shape.total_highlights,
        ),
        "",
        "### Blocking failures",
        "",
    ]
    lines.extend(_sub_bullets(verdict.blocking_failures, indent="") or [_NONE])
    lines.extend(["", "### Warnings", ""])
    lines.extend(_sub_bullets(verdict.warnings, indent="") or [_NONE])
    lines.append("")
    return lines


def _soft_failures(report: Report) -> List[str]:
    """
    Render what the Planner and Generator quietly declined to do.

    None of it is visible in the finished resume, which is why the pipeline
    captures it and why it belongs in the report.
    """
    warnings = ["{0}: {1}".format(w.code.value, w.message) for w in report.generator_warnings]
    lines = ["## Soft failures", ""]
    for label, notes in (
        ("Planner discarded", report.planner_discarded),
        ("Generator discarded", report.generator_discarded),
        ("Generator warnings", warnings),
    ):
        lines.append("### {0} ({1})".format(label, len(notes)))
        lines.append("")
        lines.extend(_sub_bullets(notes, indent="") or [_NONE])
        lines.append("")
    return lines


def render_report(report: Report) -> str:
    """Render ``report.md``: the human-readable record of the whole run."""
    lines = ["# Tailoring report", ""]
    lines.extend(_run_information(report))
    lines.extend(_job_analysis(report))
    lines.extend(_resume_plan(report))
    lines.extend(_quality_gate(report))
    lines.extend(_revision(report))
    lines.extend(_final_result(report))
    lines.extend(_soft_failures(report))
    return _document(lines)


# ----------------------------------------------------------------------
# changes.md
# ----------------------------------------------------------------------


def _lineage(change: EntityChange) -> str:
    """Return a lineage marker, from the stored ``EntitySource`` only."""
    if change.source is EntitySource.GENERATED:
        return " _(GENERATED)_"
    return ""


def _change_header(change: EntityChange) -> str:
    """Render one entity's headline: what was planned, and what happened."""
    identifier = "`{0}` ".format(change.entity_id) if change.entity_id else ""
    if change.planned_action is not None:
        planned = "planned {0}".format(change.planned_action.value)
    elif change.effective_action is EffectiveAction.GENERATED:
        # A GENERATE plan entry carries no id, so it cannot be joined to the
        # entity it produced. Saying "planned GENERATE" here would assert a
        # pairing that does not exist; the plan's own GENERATE entries are
        # listed in report.md.
        planned = "created by the Generator"
    else:
        planned = "no plan entry"
    return "- {0}{1}{2} — {3}, effective **{4}**".format(
        identifier,
        change.label,
        _lineage(change),
        planned,
        change.effective_action.value,
    )


def _text_block(label: str, items: Sequence[str]) -> List[str]:
    """
    Render a bullet list under a label, unpaired.

    Source and rewritten bullets are N:M with no correspondence between them,
    so both lists are shown and neither is diffed.
    """
    if not items:
        return []
    lines = ["  - {0}:".format(label)]
    lines.extend(_sub_bullets(items, indent="    "))
    return lines


def _change_body(change: EntityChange) -> List[str]:
    """Render everything known about one entity's change."""
    lines = []  # type: List[str]
    if change.reconciliation_note:
        lines.append("  - note: {0}".format(change.reconciliation_note))
    for label, values in (
        ("skills added", change.skills_added),
        ("skills removed", change.skills_removed),
        ("technologies added", change.technologies_added),
        ("technologies removed", change.technologies_removed),
        ("domains added", change.domains_added),
        ("domains removed", change.domains_removed),
    ):
        if values:
            lines.append("  - {0}: {1}".format(label, ", ".join(values)))
    if change.bullets_before != change.bullets_after:
        lines.extend(_text_block("before", change.bullets_before))
        lines.extend(_text_block("after", change.bullets_after))
    lines.extend("  - {0}".format(note) for note in change.revision_notes)
    lines.extend("  - reported: {0}".format(n) for n in change.soft_failure_notes)
    return lines


def _changed_sections(report: Report) -> List[str]:
    """Render every section that actually changed, in report order."""
    lines = []  # type: List[str]
    for section in CHANGE_SECTION_ORDER:
        changes = report.changes_in(section)
        if not changes:
            continue
        lines.append("## {0}".format(SECTION_LABELS[section]))
        lines.append("")
        for change in changes:
            lines.append(_change_header(change))
            lines.extend(_change_body(change))
        lines.append("")
    return lines


def _unchanged_note(report: Report) -> List[str]:
    """State which sections did not change, so silence is never ambiguous."""
    unchanged = [
        SECTION_LABELS[section]
        for section in CHANGE_SECTION_ORDER
        if not report.changes_in(section)
    ]
    if not unchanged:
        return []
    return [
        "## Unchanged",
        "",
        "- {0}".format(", ".join(unchanged)),
        "",
        "Education is never planned and never revised, so it cannot appear "
        "above.",
        "",
    ]


def render_changes(report: Report) -> str:
    """
    Render ``changes.md``: what changed in the resume, and why.

    Built from the resume plan, the revision trail, runtime entity ids and the
    stored source lineage. No Markdown is parsed and no text is diffed.
    """
    lines = [
        "# Resume changes",
        "",
        "Reconciled from the resume plan, the revision trail and each entity's "
        "runtime id and source lineage. Planner actions are what was "
        "*intended*; the effective action is what actually happened.",
        "",
    ]
    body = _changed_sections(report)
    if not body:
        lines.extend(["Nothing changed in any section.", ""])
    lines.extend(body)
    lines.extend(_unchanged_note(report))
    return _document(lines)
