"""
The reconciliation between what the Planner intended and what shipped.

This is the Reporter's only real derivation, and the one place it can lie: a
``ResumePlan`` states intent, and the Generator declines some of it. Every test
here pins a plan/outcome disagreement.
"""

import copy

from src.parser.models import EntitySource
from src.planner.models import PlanAction
from src.quality.models import ResumeSection
from src.report import EffectiveAction, Reporter
from src.revision.models import EntityKind, RevisionAction

from tests.report.conftest import (
    compression_step,
    generated_category,
    generated_project,
    make_pipeline_result,
    make_plan,
    make_revision_result,
    make_source_resume,
    passing_result,
    removal_step,
)


def _change_for(report, entity_id):
    """Return the single change record for one entity id."""
    matches = [c for c in report.changes if c.entity_id == entity_id]
    assert len(matches) == 1
    return matches[0]


def _remove_project_plan(project_id, **overrides):
    """Return a project plan entry asking for a removal."""
    entry = {
        "project_id": project_id,
        "action": "REMOVE",
        "priority": "LOW",
        "rewrite_strategy": None,
        "generation_brief": None,
        "keywords_to_include": [],
        "themes_to_emphasize": [],
        "reasoning": "Off-target for this job.",
    }
    entry.update(overrides)
    return entry


class TestPlanIntentVersusOutcome:
    """The plan is intent; presence in the resume is outcome."""

    def test_a_cancelled_removal_is_not_reported_as_a_removal(self):
        # The Generator cancels a REMOVE that no GENERATE funded, so proj_002
        # is still on the resume even though the plan asked for its removal.
        source = make_source_resume()
        plan = make_plan(
            project_plans=[
                {
                    "project_id": "proj_001",
                    "action": "KEEP",
                    "priority": "HIGH",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Relevant.",
                },
                _remove_project_plan("proj_002"),
            ]
        )
        report = Reporter().build(
            make_pipeline_result(source_resume=source, resume_plan=plan)
        )
        change = _change_for(report, "proj_002")
        assert change.planned_action is PlanAction.REMOVE
        assert change.effective_action is EffectiveAction.REMOVAL_CANCELLED
        assert change.reconciliation_note is not None

    def test_an_honoured_removal_is_reported_as_removed(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects = [generated.projects[0], generated_project()]
        plan = make_plan(
            project_plans=[
                {
                    "project_id": "proj_001",
                    "action": "KEEP",
                    "priority": "HIGH",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Relevant.",
                },
                _remove_project_plan("proj_002"),
                {
                    "project_id": None,
                    "action": "GENERATE",
                    "priority": "HIGH",
                    "rewrite_strategy": None,
                    "generation_brief": "A threat-feed aggregator.",
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Fills the gap.",
                },
            ]
        )
        report = Reporter().build(
            make_pipeline_result(
                source_resume=source, generated_resume=generated, resume_plan=plan
            )
        )
        assert _change_for(report, "proj_002").effective_action is (
            EffectiveAction.REMOVED
        )

    def test_a_rewrite_that_returned_the_source_summary_is_noted(self):
        plan = make_plan(
            summary_plan={
                "action": "REWRITE",
                "priority": "HIGH",
                "reasoning": "Lead with the role.",
                "keywords_to_include": [],
            }
        )
        report = Reporter().build(make_pipeline_result(resume_plan=plan))
        summary = report.changes[0]
        assert summary.section is ResumeSection.SUMMARY
        assert summary.effective_action is EffectiveAction.REWRITTEN
        assert "unchanged" in summary.reconciliation_note


class TestSoftFailureAttribution:
    """The Generator's own notes are filed under the entity they name."""

    def test_a_note_naming_an_entity_is_filed_under_it(self):
        note = (
            "skill category skill_002 ('Backend'): removal of 'Caching' was "
            "cancelled — only 1 skill was available to replace it"
        )
        report = Reporter().build(
            make_pipeline_result(generator_discarded=[note])
        )
        assert _change_for(report, "skill_002").soft_failure_notes == [note]
        assert _change_for(report, "skill_001").soft_failure_notes == []
        assert "- reported: skill category skill_002" in Reporter().render_changes(
            report
        )

    def test_a_note_naming_no_entity_is_filed_under_none(self):
        # It still reaches the reader through report.md's soft-failures
        # section; what it must not do is attach to an arbitrary entity.
        note = "the summary lost an anchor during the rewrite"
        report = Reporter().build(
            make_pipeline_result(generator_discarded=[note])
        )
        for change in report.changes:
            assert change.soft_failure_notes == []
        assert note in Reporter().render_report(report)


class TestGeneratedLineage:
    """Generated entities are identified by ``EntitySource``, never inferred."""

    def test_a_generated_project_is_reported_as_generated(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects.append(generated_project())
        report = Reporter().build(
            make_pipeline_result(source_resume=source, generated_resume=generated)
        )
        change = _change_for(report, "proj_003")
        assert change.effective_action is EffectiveAction.GENERATED
        assert change.source is EntitySource.GENERATED
        assert report.final_shape.generated_projects == ["proj_003"]

    def test_a_generated_skill_category_is_reported_as_generated(self):
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.skills.append(generated_category())
        report = Reporter().build(
            make_pipeline_result(source_resume=source, generated_resume=generated)
        )
        change = _change_for(report, "skill_003")
        assert change.effective_action is EffectiveAction.GENERATED
        assert change.skills_added == ["Splunk", "Suricata"]
        assert report.final_shape.generated_skill_categories == ["skill_003"]

    def test_a_generated_entity_claims_no_plan_pairing(self):
        # A GENERATE plan entry carries project_id=None by model invariant, so
        # it cannot be joined to the entity it produced. Reporting "planned
        # GENERATE" against a minted project would assert a pairing that does
        # not exist.
        source = make_source_resume()
        generated = copy.deepcopy(source)
        generated.projects.append(generated_project())
        report = Reporter().build(
            make_pipeline_result(source_resume=source, generated_resume=generated)
        )
        change = _change_for(report, "proj_003")
        assert change.planned_action is None
        assert change.effective_action is EffectiveAction.GENERATED
        rendered = Reporter().render_changes(report)
        assert "created by the Generator" in rendered
        assert "planned GENERATE" not in rendered

    def test_the_reporter_never_invents_a_source_value(self):
        # Nothing the Parser produced is GENERATED, so an untouched run must
        # report no generated entities at all.
        report = Reporter().build(make_pipeline_result())
        assert report.generated_shape.generated_projects == []
        assert report.generated_shape.generated_skill_categories == []
        for change in report.changes:
            assert change.source is not EntitySource.GENERATED


class TestRevisionEngineChanges:
    """Trimming is attributed to the Revision Engine, not to the plan."""

    def test_a_bullet_removal_is_attributed_to_the_entity(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.projects[0].highlights = final.projects[0].highlights[:3]
        revision = make_revision_result(
            final,
            trail=[
                removal_step(
                    1,
                    RevisionAction.REMOVE_BULLET,
                    "proj_001",
                    EntityKind.PROJECT,
                    page_count=1,
                    spill=0,
                    passed=True,
                    detail="Delivered project item 4.",
                )
            ],
            gate_results=[passing_result()],
        )
        report = Reporter().build(make_pipeline_result(revision=revision))
        notes = _change_for(report, "proj_001").revision_notes
        assert len(notes) == 1
        assert "Removed a bullet" in notes[0]
        assert "Delivered project item 4." in notes[0]

    def test_a_project_removed_by_trimming_is_not_reported_as_planned(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.projects = final.projects[:1]
        revision = make_revision_result(
            final,
            trail=[
                removal_step(
                    1,
                    RevisionAction.REMOVE_PROJECT,
                    "proj_002",
                    EntityKind.PROJECT,
                    page_count=1,
                    spill=0,
                    passed=True,
                    detail="Project 2",
                )
            ],
            gate_results=[passing_result()],
        )
        report = Reporter().build(make_pipeline_result(revision=revision))
        change = _change_for(report, "proj_002")
        assert change.effective_action is EffectiveAction.TRIMMED_FOR_PAGE_FIT
        assert change.planned_action is PlanAction.KEEP

    def test_a_skill_removal_shows_which_skills_went(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.skills[1].skills = final.skills[1].skills[:2]
        dropped = source.skills[1].skills[2:]
        revision = make_revision_result(
            final,
            trail=[
                removal_step(
                    1,
                    RevisionAction.REMOVE_SKILLS,
                    "skill_002",
                    EntityKind.SKILL_CATEGORY,
                    page_count=1,
                    spill=0,
                    passed=True,
                    detail="Category 2",
                )
            ],
            gate_results=[passing_result()],
        )
        report = Reporter().build(make_pipeline_result(revision=revision))
        change = _change_for(report, "skill_002")
        assert change.skills_removed == dropped
        assert change.skills_added == []

    def test_a_compression_pass_is_attributed_by_bullet_id(self):
        source = make_source_resume()
        final = copy.deepcopy(source)
        final.experiences[0].highlights[1] = "Shortened bullet."
        revision = make_revision_result(
            final,
            trail=[
                compression_step(
                    1, ["exp_001:bullet_2"], page_count=1, spill=0, passed=True
                )
            ],
            gate_results=[passing_result()],
            compression_passes=1,
            llm_calls=1,
        )
        report = Reporter().build(make_pipeline_result(revision=revision))
        notes = _change_for(report, "exp_001").revision_notes
        assert notes == ["Compressed 1 bullet(s) to satisfy page-fit constraints."]
        # The bullet belongs to exp_001 only; exp_002 must not claim it.
        assert _change_for(report, "exp_002").revision_notes == []
