"""
Behavioural tests for the ResumeGenerator.

Covers the four plan actions in every section that supports them, mode
handling, ID minting, entity sourcing, immutability, and the mapping from
provider failures to typed exceptions.
"""

import copy

import pytest

from src.generator import (
    GenerationConstraintError,
    GeneratorError,
    GeneratorResponseValidationError,
    InvalidGeneratorJSON,
    InvalidGeneratorResponse,
    ResumeGenerator,
)
from src.parser.models import EntitySource
from src.planner.models import PlanningMode

from .conftest import (
    FailingProvider,
    SequencedProvider,
    experience_entry,
    experiences_response,
    make_job_analysis,
    make_plan,
    make_resume,
    project_entry,
    projects_response,
    summary_response,
)


def _generate(responses, plan=None, resume=None, **kwargs):
    """Run a generation against a queued provider, returning both."""
    provider = SequencedProvider(responses)
    generator = ResumeGenerator(provider)
    result = generator.generate(
        source_resume=resume if resume is not None else make_resume(),
        job_analysis=make_job_analysis(),
        resume_plan=plan if plan is not None else make_plan(),
        **kwargs,
    )
    return result, generator, provider


# ---------------------------------------------------------------------------
# KEEP
# ---------------------------------------------------------------------------


class TestKeepEverything:
    def test_makes_no_llm_calls(self):
        _, _, provider = _generate([])
        assert provider.call_count == 0

    def test_reproduces_the_source(self):
        source = make_resume()
        result, _, _ = _generate([], resume=source)
        assert result.summary == source.summary
        assert [s.category for s in result.skills] == ["Languages", "Cloud"]
        assert [p.id for p in result.projects] == ["proj_001", "proj_002"]
        assert [e.role for e in result.experiences] == [
            "Software Engineering Intern",
            "Software Engineer",
        ]

    def test_produces_no_validator_warnings(self):
        _, generator, _ = _generate([])
        assert generator.last_warnings == []


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_source_resume_is_not_mutated(self):
        source = make_resume()
        before = copy.deepcopy(source)

        plan = make_plan(
            summary_plan={
                "action": "REWRITE",
                "priority": "HIGH",
                "reasoning": "Sharpen for the target role.",
                "keywords_to_include": ["Python"],
            }
        )
        _generate(
            [summary_response("A rewritten summary " + "word " * 25)],
            plan=plan,
            resume=source,
        )

        assert source == before

    def test_contact_education_metadata_copied_verbatim(self):
        source = make_resume()
        result, _, _ = _generate([], resume=source)
        assert result.contact == source.contact
        assert result.education == source.education
        assert result.metadata == source.metadata

    def test_contact_is_a_copy_not_a_reference(self):
        source = make_resume()
        result, _, _ = _generate([], resume=source)
        result.contact.name = "Someone Else"
        assert source.contact.name == "Jane Doe"

    def test_experience_count_and_order_come_from_the_source(self):
        # The model returned only one experience; the other is preserved.
        plan = _rewrite_experience_plan("exp_002")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002"))], plan=plan
        )
        assert len(result.experiences) == 2
        assert [e.id for e in result.experiences] == ["exp_001", "exp_002"]

    def test_immutable_experience_fields_are_reimposed(self):
        source = make_resume()
        plan = _rewrite_experience_plan("exp_002")
        # The model tries to change everything it is not allowed to.
        result, _, _ = _generate(
            [
                experiences_response(
                    experience_entry(
                        "exp_002",
                        role="Backend Engineer",
                        technologies=["Python"],
                        domains=["Backend"],
                        highlights=["Shipped a payments service."],
                    )
                )
            ],
            plan=plan,
            resume=source,
        )

        rewritten = result.experiences[1]
        original = source.experiences[1]
        assert rewritten.company == original.company
        assert rewritten.duration == original.duration
        assert rewritten.employment_type == original.employment_type
        assert rewritten.location == original.location
        assert rewritten.id == original.id
        assert rewritten.source == original.source


def _notes_matching(generator, needle):
    """Notes mentioning `needle`. Lets a test assert about its own concern
    without breaking when an unrelated note is added."""
    return [n for n in generator.last_discarded if needle in n]


def _by_id(entities, entity_id):
    """Select an entity by id; positions now depend on priority ordering."""
    return next(e for e in entities if e.id == entity_id)


def _rewrite_experience_plan(experience_id: str, mode: str = "AGGRESSIVE"):
    """A plan that rewrites one experience and keeps everything else."""
    plan_payload = {
        "mode": mode,
        "experience_plans": [
            {
                "experience_id": "exp_001",
                "action": "KEEP",
                "priority": "LOW",
                "rewrite_strategy": None,
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "Internship is less relevant.",
            },
            {
                "experience_id": experience_id,
                "action": "REWRITE",
                "priority": "CRITICAL",
                "rewrite_strategy": "Lead with payments and scale.",
                "keywords_to_include": ["Python"],
                "themes_to_emphasize": ["Backend"],
                "reasoning": "Closest match to the target role.",
            },
        ],
    }
    if experience_id == "exp_001":
        plan_payload["experience_plans"].reverse()
        plan_payload["experience_plans"][1]["experience_id"] = "exp_002"
    return make_plan(**plan_payload)


# ---------------------------------------------------------------------------
# Role mutability
# ---------------------------------------------------------------------------


class TestRoleMutability:
    def test_aggressive_accepts_a_retitled_role(self):
        plan = _rewrite_experience_plan("exp_002", mode="AGGRESSIVE")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002", role="Backend Engineer"))],
            plan=plan,
        )
        assert result.experiences[1].role == "Backend Engineer"

    def test_strict_reimposes_the_source_role(self):
        # The model was told not to change the role and did anyway. Python
        # overrides it rather than failing the whole generation.
        plan = _rewrite_experience_plan("exp_002", mode="STRICT")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002", role="Backend Engineer"))],
            plan=plan,
        )
        assert result.experiences[1].role == "Software Engineer"

    def test_blank_role_falls_back_to_the_source(self):
        plan = _rewrite_experience_plan("exp_002", mode="AGGRESSIVE")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002", role="   "))],
            plan=plan,
        )
        assert result.experiences[1].role == "Software Engineer"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    def _skills_plan(self, *entries, mode="AGGRESSIVE"):
        return make_plan(mode=mode, skills_plans=list(entries))

    def _keep(self, category_id):
        return {
            "category_id": category_id,
            "action": "KEEP",
            "priority": "MEDIUM",
            "new_category_name": None,
            "skills_to_add": [],
            "skills_to_remove": [],
            "reasoning": "Already relevant.",
        }

    def test_skills_never_call_the_model(self):
        plan = self._skills_plan(
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Container & Orchestration",
                "skills_to_add": ["Docker", "Kubernetes"],
                "skills_to_remove": [],
                "reasoning": "The job needs container tooling.",
            },
            self._keep("skill_001"),
            self._keep("skill_002"),
        )
        _, _, provider = _generate([], plan=plan)
        assert provider.call_count == 0

    def test_generated_category_gets_minted_id_and_source(self):
        plan = self._skills_plan(
            self._keep("skill_001"),
            self._keep("skill_002"),
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Container & Orchestration",
                "skills_to_add": ["Docker", "Kubernetes"],
                "skills_to_remove": [],
                "reasoning": "The job needs container tooling.",
            },
        )
        result, _, _ = _generate([], plan=plan)

        new_category = _by_id(result.skills, "skill_003")
        assert new_category.source == EntitySource.GENERATED
        assert new_category.category == "Container & Orchestration"
        assert set(new_category.skills) == {"Docker", "Kubernetes"}

    def test_rewrite_adds_and_removes_skills(self):
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": None,
                "skills_to_add": ["Rust"],
                "skills_to_remove": ["Go"],
                "reasoning": "Match the job's language list.",
            },
            self._keep("skill_002"),
        )
        result, _, _ = _generate([], plan=plan)

        languages = result.skills[0]
        assert "Rust" in languages.skills
        assert "Go" not in languages.skills
        assert "Python" in languages.skills

    def test_rewrite_preserves_id_and_source(self):
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": "Backend & Distributed Systems",
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Match the job's phrasing.",
            },
            self._keep("skill_002"),
        )
        result, _, _ = _generate([], plan=plan)

        renamed = result.skills[0]
        assert renamed.id == "skill_001"
        assert renamed.source == EntitySource.CANONICAL
        assert renamed.category == "Backend & Distributed Systems"

    def _remove(self, category_id):
        return {
            "category_id": category_id,
            "action": "REMOVE",
            "priority": "LOW",
            "new_category_name": None,
            "skills_to_add": [],
            "skills_to_remove": [],
            "reasoning": "Not relevant to this job.",
        }

    def _generate_category(self, name="Container & Orchestration", skills=None):
        return {
            "category_id": None,
            "action": "GENERATE",
            "priority": "HIGH",
            "new_category_name": name,
            "skills_to_add": skills or ["Docker", "Kubernetes"],
            "skills_to_remove": [],
            "reasoning": "The job needs container tooling.",
        }

    def test_unfunded_removal_is_cancelled(self):
        # Nothing is generated to take the slot, so the category stays. A plan
        # that deletes without generating asks the resume to shrink for free.
        plan = self._skills_plan(self._keep("skill_001"), self._remove("skill_002"))
        result, generator, _ = _generate([], plan=plan)

        assert [c.id for c in result.skills] == ["skill_001", "skill_002"]
        assert any("skill_002" in note for note in generator.last_discarded)

    def test_a_generated_category_funds_a_removal(self):
        plan = self._skills_plan(
            self._keep("skill_001"),
            self._remove("skill_002"),
            self._generate_category(),
        )
        result, generator, _ = _generate([], plan=plan)

        assert sorted(c.id for c in result.skills) == ["skill_001", "skill_003"]
        assert not _notes_matching(generator, "cancelled")

    def test_removals_beyond_the_budget_are_cancelled(self):
        # Two removals, one generated category: the first removal is funded,
        # the second is not.
        plan = self._skills_plan(
            self._remove("skill_001"),
            self._remove("skill_002"),
            self._generate_category(),
        )
        result, generator, _ = _generate([], plan=plan)

        assert sorted(c.id for c in result.skills) == ["skill_002", "skill_003"]
        assert any("skill_002" in note for note in generator.last_discarded)

    def test_job_keywords_are_ordered_first(self):
        # The job requires Python and AWS; Docker is listed as a technology.
        # Within "Cloud", AWS should precede Docker regardless of source order.
        plan = self._skills_plan(
            self._keep("skill_001"),
            {
                "category_id": "skill_002",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Surface the job's stack first.",
            },
        )
        result, _, _ = _generate([], plan=plan)
        assert _by_id(result.skills, "skill_002").skills == ["AWS", "Docker"]

    def test_a_rewrite_with_no_additions_keeps_its_skills(self):
        # The plan intended a trade. Its additions were refused upstream, so
        # executing the removal half alone would turn the trade into a
        # deletion — which is how five real skills once vanished with nothing
        # taking their place.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": ["Python", "Go"],
                "reasoning": "None of these match the job.",
            },
            self._keep("skill_002"),
        )
        result, generator, _ = _generate([], plan=plan)

        assert result.skills[0].skills == ["Python", "Go"]
        assert any("skill_001" in note for note in generator.last_discarded)

    def test_a_cancelled_rewrite_also_drops_its_rename(self):
        # A category renamed for skills that never arrived is mislabelled.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": "Testing & Quality Assurance",
                "skills_to_add": [],
                "skills_to_remove": ["Python", "Go"],
                "reasoning": "Retarget to the job's testing focus.",
            },
            self._keep("skill_002"),
        )
        result, _, _ = _generate([], plan=plan)

        assert result.skills[0].category == "Languages"
        assert result.skills[0].skills == ["Python", "Go"]

    def test_a_rename_without_removals_still_applies(self):
        # Renaming deletes nothing, so it is not blocked.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": "Backend & API Development",
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Match the job's phrasing.",
            },
            self._keep("skill_002"),
        )
        result, _, _ = _generate([], plan=plan)

        assert result.skills[0].category == "Backend & API Development"
        assert result.skills[0].skills == ["Python", "Go"]

    def test_no_skill_categories_at_all_raises(self):
        # Defensive: the planner guarantees total coverage, so this is only
        # reachable from a hand-built plan.
        plan = self._skills_plan()
        generator = ResumeGenerator(SequencedProvider([]))
        with pytest.raises(GenerationConstraintError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )

    def test_a_lopsided_trade_splits_into_a_new_category(self):
        # Five out, one in. Forcing the incoming skill into the existing
        # category would club unrelated things together under one heading, so
        # it gets its own category and the original is left intact.
        resume = make_resume()
        resume.skills[0] = resume.skills[0].model_copy(
            update={
                "category": "Concepts",
                "skills": ["Distributed Systems", "API Design", "Caching"],
            }
        )
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": "Development Practices & Standards",
                "skills_to_add": ["Performance Profiling"],
                "skills_to_remove": ["Distributed Systems", "API Design", "Caching"],
                "reasoning": "Retarget to the job's process focus.",
            },
            self._keep("skill_002"),
        )
        result, generator, _ = _generate([], plan=plan, resume=resume)

        original = _by_id(result.skills, "skill_001")
        assert original.category == "Concepts"
        assert original.skills == ["Distributed Systems", "API Design", "Caching"]

        split = _by_id(result.skills, "skill_003")
        assert split.category == "Development Practices & Standards"
        assert split.skills == ["Performance Profiling"]
        assert split.source == EntitySource.GENERATED
        assert any("skill_001" in note for note in generator.last_discarded)

    def test_an_even_trade_happens_in_place(self):
        # One out, one in: no clubbing risk, so no split.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": None,
                "skills_to_add": ["Rust"],
                "skills_to_remove": ["Go"],
                "reasoning": "Match the job's language list.",
            },
            self._keep("skill_002"),
        )
        result, generator, _ = _generate([], plan=plan)

        languages = _by_id(result.skills, "skill_001")
        assert "Rust" in languages.skills
        assert "Go" not in languages.skills
        assert len(result.skills) == 2
        assert not _notes_matching(generator, "cancelled")

    def test_a_lopsided_trade_without_a_name_merges_in_place(self):
        # No rename means the additions were meant to sit beside the existing
        # skills, so there is nothing to split off.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "new_category_name": None,
                "skills_to_add": ["Rust"],
                "skills_to_remove": ["Python", "Go"],
                "reasoning": "Match the job's language list.",
            },
            self._keep("skill_002"),
        )
        result, _, _ = _generate([], plan=plan)

        languages = _by_id(result.skills, "skill_001")
        assert set(languages.skills) == {"Python", "Go"}
        assert len(result.skills) == 2

    def test_a_kept_category_still_gets_its_skills_ordered(self):
        # KEEP returns the source category untouched, so without ordering at
        # the end it would ship in source order — burying the job's own
        # vocabulary at the end of the line a recruiter skims.
        resume = make_resume()
        resume.skills[1] = resume.skills[1].model_copy(
            update={"skills": ["Docker", "AWS"]}
        )
        plan = self._skills_plan(self._keep("skill_001"), self._keep("skill_002"))
        result, _, _ = _generate([], plan=plan, resume=resume)

        # The job requires AWS and lists Docker only as a technology.
        assert _by_id(result.skills, "skill_002").skills == ["AWS", "Docker"]

    def test_a_cancelled_removal_still_gets_its_skills_ordered(self):
        resume = make_resume()
        resume.skills[1] = resume.skills[1].model_copy(
            update={"skills": ["Docker", "AWS"]}
        )
        plan = self._skills_plan(self._keep("skill_001"), self._remove("skill_002"))
        result, _, _ = _generate([], plan=plan, resume=resume)

        assert _by_id(result.skills, "skill_002").skills == ["AWS", "Docker"]

    def test_categories_are_ordered_by_priority(self):
        # The Quality Gate trims from the bottom, so least relevant goes last.
        plan = self._skills_plan(
            dict(self._keep("skill_001"), priority="LOW"),
            dict(self._keep("skill_002"), priority="CRITICAL"),
        )
        result, _, _ = _generate([], plan=plan)
        assert [c.id for c in result.skills] == ["skill_002", "skill_001"]

    def test_equal_priority_keeps_plan_order(self):
        plan = self._skills_plan(
            dict(self._keep("skill_001"), priority="HIGH"),
            dict(self._keep("skill_002"), priority="HIGH"),
        )
        result, _, _ = _generate([], plan=plan)
        assert [c.id for c in result.skills] == ["skill_001", "skill_002"]

    def test_minted_id_survives_a_removal(self):
        # skill_001 is removed and a category generated. The new id must be
        # skill_003, not skill_002, which skill_002 already owns.
        plan = self._skills_plan(
            {
                "category_id": "skill_001",
                "action": "REMOVE",
                "priority": "LOW",
                "new_category_name": None,
                "skills_to_add": [],
                "skills_to_remove": [],
                "reasoning": "Not relevant.",
            },
            self._keep("skill_002"),
            {
                "category_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "new_category_name": "Container & Orchestration",
                "skills_to_add": ["Docker"],
                "skills_to_remove": [],
                "reasoning": "The job needs container tooling.",
            },
        )
        result, _, _ = _generate([], plan=plan)
        assert sorted(c.id for c in result.skills) == ["skill_002", "skill_003"]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _project_plan(*entries, mode="AGGRESSIVE"):
    return make_plan(mode=mode, project_plans=list(entries))


def _remove_project(project_id):
    return {
        "project_id": project_id,
        "action": "REMOVE",
        "priority": "LOW",
        "rewrite_strategy": None,
        "generation_brief": None,
        "keywords_to_include": [],
        "themes_to_emphasize": [],
        "reasoning": "Not relevant.",
    }


def _keep_project(project_id):
    return {
        "project_id": project_id,
        "action": "KEEP",
        "priority": "MEDIUM",
        "rewrite_strategy": None,
        "generation_brief": None,
        "keywords_to_include": [],
        "themes_to_emphasize": [],
        "reasoning": "Still relevant.",
    }


class TestProjects:
    def test_generated_project_gets_minted_id_and_source(self):
        plan = _project_plan(
            _keep_project("proj_001"),
            _keep_project("proj_002"),
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "An event-driven microservices demo.",
                "keywords_to_include": ["AWS"],
                "themes_to_emphasize": ["Backend"],
                "reasoning": "The job wants event-driven experience.",
            },
        )
        result, _, _ = _generate(
            [
                projects_response(
                    project_entry(None, name="Event Bus", type="Open Source")
                )
            ],
            plan=plan,
        )

        new_project = _by_id(result.projects, "proj_003")
        assert new_project.source == EntitySource.GENERATED
        assert new_project.name == "Event Bus"

    def test_generated_project_never_gets_a_repository(self):
        plan = _project_plan(
            _keep_project("proj_001"),
            _keep_project("proj_002"),
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "An event-driven microservices demo.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "The job wants event-driven experience.",
            },
        )
        result, _, _ = _generate(
            [projects_response(project_entry(None, name="Event Bus"))], plan=plan
        )
        assert _by_id(result.projects, "proj_003").repository is None

    def test_rewrite_preserves_id_source_and_repository(self):
        plan = _project_plan(
            {
                "project_id": "proj_001",
                "action": "REWRITE",
                "priority": "HIGH",
                "rewrite_strategy": "Lead with the Python tooling angle.",
                "generation_brief": None,
                "keywords_to_include": ["Python"],
                "themes_to_emphasize": [],
                "reasoning": "Closest to the job's tooling work.",
            },
            _keep_project("proj_002"),
        )
        result, _, _ = _generate(
            [
                projects_response(
                    project_entry("proj_001", name="Task Tracker CLI")
                )
            ],
            plan=plan,
        )

        rewritten = result.projects[0]
        assert rewritten.id == "proj_001"
        assert rewritten.source == EntitySource.CANONICAL
        assert rewritten.repository == "github.com/janedoe/task-tracker"
        assert rewritten.name == "Task Tracker CLI"

    def test_unfunded_project_removal_is_cancelled(self):
        # Dropping a real project with nothing to show in its place only makes
        # the resume thinner.
        plan = _project_plan(_remove_project("proj_001"), _keep_project("proj_002"))
        result, generator, _ = _generate([], plan=plan)

        assert sorted(p.id for p in result.projects) == ["proj_001", "proj_002"]
        assert any("proj_001" in note for note in generator.last_discarded)

    def test_a_generated_project_funds_a_removal(self):
        plan = _project_plan(
            _remove_project("proj_001"),
            _keep_project("proj_002"),
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "An event-driven microservices demo.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "The job wants event-driven experience.",
            },
        )
        result, generator, _ = _generate(
            [projects_response(project_entry(None, name="Event Bus"))], plan=plan
        )

        assert sorted(p.id for p in result.projects) == ["proj_002", "proj_003"]
        assert not _notes_matching(generator, "cancelled")

    def test_project_removals_beyond_the_budget_are_cancelled(self):
        source = make_resume()
        source.projects.append(
            copy.deepcopy(source.projects[0]).model_copy(update={"id": "proj_003"})
        )
        plan = _project_plan(
            _remove_project("proj_001"),
            _remove_project("proj_002"),
            _keep_project("proj_003"),
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "An event-driven microservices demo.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "The job wants event-driven experience.",
            },
        )
        result, generator, _ = _generate(
            [projects_response(project_entry(None, name="Event Bus"))],
            plan=plan,
            resume=source,
        )

        # One generated project funds one removal; the second is cancelled.
        assert sorted(p.id for p in result.projects) == ["proj_002", "proj_003", "proj_004"]
        assert any("proj_002" in note for note in generator.last_discarded)

    def test_projects_are_ordered_by_priority(self):
        plan = _project_plan(
            dict(_keep_project("proj_001"), priority="LOW"),
            dict(_keep_project("proj_002"), priority="CRITICAL"),
        )
        result, _, _ = _generate([], plan=plan)
        assert [p.id for p in result.projects] == ["proj_002", "proj_001"]

    def test_equal_priority_keeps_plan_order(self):
        plan = _project_plan(
            dict(_keep_project("proj_001"), priority="MEDIUM"),
            dict(_keep_project("proj_002"), priority="MEDIUM"),
        )
        result, _, _ = _generate([], plan=plan)
        assert [p.id for p in result.projects] == ["proj_001", "proj_002"]

    def test_experiences_are_never_reordered(self):
        # Experiences are the one section that must not be sorted: the
        # validator compares them positionally against the source, and a
        # resume reads in reverse-chronological order regardless of relevance.
        plan = make_plan(
            experience_plans=[
                dict(
                    experience_id="exp_001",
                    action="KEEP",
                    priority="LOW",
                    rewrite_strategy=None,
                    keywords_to_include=[],
                    themes_to_emphasize=[],
                    reasoning="Less relevant.",
                ),
                dict(
                    experience_id="exp_002",
                    action="KEEP",
                    priority="CRITICAL",
                    rewrite_strategy=None,
                    keywords_to_include=[],
                    themes_to_emphasize=[],
                    reasoning="Closest match.",
                ),
            ]
        )
        result, _, _ = _generate([], plan=plan)
        assert [e.id for e in result.experiences] == ["exp_001", "exp_002"]

    def test_no_projects_at_all_raises(self):
        # Defensive: the planner guarantees total coverage, so this is only
        # reachable from a hand-built plan.
        plan = _project_plan()
        generator = ResumeGenerator(SequencedProvider([]))
        with pytest.raises(GenerationConstraintError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )

    def test_missing_generated_project_raises(self):
        plan = _project_plan(
            _keep_project("proj_001"),
            _keep_project("proj_002"),
            {
                "project_id": None,
                "action": "GENERATE",
                "priority": "HIGH",
                "rewrite_strategy": None,
                "generation_brief": "An event-driven microservices demo.",
                "keywords_to_include": [],
                "themes_to_emphasize": [],
                "reasoning": "The job wants event-driven experience.",
            },
        )
        provider = SequencedProvider([projects_response()])
        generator = ResumeGenerator(provider)
        with pytest.raises(InvalidGeneratorResponse):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )


# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------


class TestModeHandling:
    def test_mode_defaults_to_the_plan(self):
        plan = _rewrite_experience_plan("exp_002", mode="STRICT")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002", role="Backend Engineer"))],
            plan=plan,
        )
        # Strict re-imposed the source role without an explicit mode argument.
        assert result.experiences[1].role == "Software Engineer"

    def test_matching_explicit_mode_is_accepted(self):
        plan = _rewrite_experience_plan("exp_002", mode="AGGRESSIVE")
        result, _, _ = _generate(
            [experiences_response(experience_entry("exp_002", role="Backend Engineer"))],
            plan=plan,
            mode=PlanningMode.AGGRESSIVE,
        )
        assert result.experiences[1].role == "Backend Engineer"

    def test_disagreeing_mode_raises(self):
        plan = make_plan(mode="STRICT")
        generator = ResumeGenerator(SequencedProvider([]))
        with pytest.raises(GeneratorError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
                mode=PlanningMode.AGGRESSIVE,
            )


# ---------------------------------------------------------------------------
# Transport failures
# ---------------------------------------------------------------------------


def _summary_rewrite_plan(mode="AGGRESSIVE"):
    return make_plan(
        mode=mode,
        summary_plan={
            "action": "REWRITE",
            "priority": "HIGH",
            "reasoning": "Sharpen for the target role.",
            "keywords_to_include": ["Python"],
        },
    )


class TestTransportFailures:
    def _run(self, provider):
        generator = ResumeGenerator(provider)
        return generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=_summary_rewrite_plan(),
        )

    def test_provider_exception_is_wrapped(self):
        with pytest.raises(GeneratorError):
            self._run(FailingProvider(RuntimeError("connection reset")))

    def test_sdk_error_does_not_leak(self):
        try:
            self._run(FailingProvider(RuntimeError("connection reset")))
        except GeneratorError:
            pass
        else:
            pytest.fail("expected GeneratorError")

    def test_empty_response_raises(self):
        with pytest.raises(InvalidGeneratorResponse):
            self._run(SequencedProvider(["   "]))

    def test_unparseable_json_raises(self):
        with pytest.raises(InvalidGeneratorJSON):
            self._run(SequencedProvider(["not json at all"]))

    def test_json_array_raises(self):
        with pytest.raises(InvalidGeneratorJSON):
            self._run(SequencedProvider(['["a", "b"]']))

    def test_schema_violation_raises(self):
        with pytest.raises(InvalidGeneratorResponse):
            self._run(SequencedProvider(['{"unexpected_key": "value"}']))

    def test_empty_summary_raises(self):
        with pytest.raises(InvalidGeneratorResponse):
            self._run(SequencedProvider([summary_response("   ")]))

    def test_unknown_experience_id_raises(self):
        plan = _rewrite_experience_plan("exp_002")
        provider = SequencedProvider(
            [experiences_response(experience_entry("exp_999"))]
        )
        generator = ResumeGenerator(provider)
        with pytest.raises(InvalidGeneratorResponse):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )

    def test_skipped_experience_raises(self):
        plan = _rewrite_experience_plan("exp_002")
        provider = SequencedProvider([experiences_response()])
        generator = ResumeGenerator(provider)
        with pytest.raises(InvalidGeneratorResponse):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_output_raises(self):
        # An empty highlights list fails the validator.
        plan = _rewrite_experience_plan("exp_002")
        provider = SequencedProvider(
            [experiences_response(experience_entry("exp_002", highlights=[]))]
        )
        generator = ResumeGenerator(provider)
        with pytest.raises(GeneratorResponseValidationError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=plan,
            )

    def test_warnings_are_exposed_not_raised(self):
        long_summary = "Word " * 200
        _, generator, _ = _generate(
            [summary_response(long_summary)], plan=_summary_rewrite_plan()
        )
        codes = [w.code.value for w in generator.last_warnings]
        assert "SUMMARY_TOO_LONG" in codes


# ---------------------------------------------------------------------------
# Statelessness
# ---------------------------------------------------------------------------


class TestSummaryAnchors:
    """
    A summary that trades concrete facts for a job title gains nothing.

    Reported rather than raised: prose judgement is not a correctness rule.
    """

    def _plan(self):
        return make_plan(
            summary_plan={
                "action": "REWRITE",
                "priority": "HIGH",
                "reasoning": "Retarget to the job.",
                "keywords_to_include": [],
            }
        )

    def _summary_mentioning(self, text):
        return summary_response(text + " " + "filler " * 25)

    def test_dropping_the_employer_is_reported(self):
        resume = make_resume()
        resume.summary = "Backend engineer with two years at Acme Corp using Python."
        _, generator, _ = _generate(
            [self._summary_mentioning("Application Software Development professional.")],
            plan=self._plan(),
            resume=resume,
        )
        assert any("Acme Corp" in note for note in generator.last_discarded)

    def test_keeping_the_employer_is_not_reported(self):
        resume = make_resume()
        resume.summary = "Backend engineer with two years at Acme Corp using Python."
        _, generator, _ = _generate(
            [self._summary_mentioning("Backend engineer at Acme Corp using Python.")],
            plan=self._plan(),
            resume=resume,
        )
        assert not _notes_matching(generator, "summary")

    def test_dropping_every_named_technology_is_reported(self):
        resume = make_resume()
        resume.summary = "Backend engineer at Acme Corp building services in Python."
        _, generator, _ = _generate(
            [self._summary_mentioning("Engineer at Acme Corp delivering features.")],
            plan=self._plan(),
            resume=resume,
        )
        assert any("technology" in note for note in generator.last_discarded)

    def test_keeping_one_named_technology_is_enough(self):
        resume = make_resume()
        resume.summary = "Backend engineer at Acme Corp using Python and Go."
        _, generator, _ = _generate(
            [self._summary_mentioning("Engineer at Acme Corp shipping Python services.")],
            plan=self._plan(),
            resume=resume,
        )
        assert not _notes_matching(generator, "summary")

    def test_a_kept_summary_is_never_reported(self):
        # KEEP does not call the model at all.
        _, generator, _ = _generate([])
        assert not _notes_matching(generator, "summary")


class TestStatelessness:
    def test_warnings_reset_between_calls(self):
        provider = SequencedProvider([summary_response("Word " * 200)])
        generator = ResumeGenerator(provider)
        generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=_summary_rewrite_plan(),
        )
        assert generator.last_warnings

        # A second, all-KEEP generation must not inherit the first's warnings.
        generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=make_plan(),
        )
        assert generator.last_warnings == []

    def test_repeated_calls_produce_equal_output(self):
        generator = ResumeGenerator(SequencedProvider([]))
        first = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=make_plan(),
        )
        second = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=make_plan(),
        )
        assert first == second


# ---------------------------------------------------------------------------
# Bullet ordering
# ---------------------------------------------------------------------------


class TestHighlightOrdering:
    """
    The two experiences cannot be deleted, but their bullets can be trimmed —
    from the bottom. So the order *within* each one decides what survives.

    Scored on two signals only: how many of the job's terms the bullet uses,
    and whether it carries a number. The sort is stable, so equal scores keep
    the order the model wrote them in.
    """

    def _plan(self):
        return _rewrite_experience_plan("exp_002")

    def _with_highlights(self, *highlights):
        result, _, _ = _generate(
            [
                experiences_response(
                    experience_entry("exp_002", highlights=list(highlights))
                )
            ],
            plan=self._plan(),
        )
        return result.experiences[1].highlights

    def test_a_job_term_beats_no_job_term(self):
        # The job requires Python and AWS.
        ordered = self._with_highlights(
            "Wrote documentation for the team.",
            "Built services in Python.",
        )
        assert ordered[0] == "Built services in Python."

    def test_a_metric_beats_a_bare_bullet(self):
        ordered = self._with_highlights(
            "Improved the deployment process.",
            "Cut latency by 30%.",
        )
        assert ordered[0] == "Cut latency by 30%."

    def test_more_job_terms_outrank_a_lone_metric(self):
        # A number is persuasive, not decisive: METRIC_WEIGHT is 2, so three
        # job terms win.
        ordered = self._with_highlights(
            "Reduced cost by 30%.",
            "Built Python and AWS services for the backend.",
        )
        assert ordered[0] == "Built Python and AWS services for the backend."

    def test_equal_scores_keep_the_models_order(self):
        ordered = self._with_highlights(
            "Built services in Python.",
            "Deployed services with Python.",
        )
        assert ordered == [
            "Built services in Python.",
            "Deployed services with Python.",
        ]

    def test_the_weakest_bullet_ends_up_last(self):
        ordered = self._with_highlights(
            "Attended team meetings.",
            "Cut Python API latency by 30%.",
            "Shipped an AWS backend service.",
        )
        assert ordered[-1] == "Attended team meetings."

    def test_a_single_bullet_is_untouched(self):
        assert self._with_highlights("Only one bullet.") == ["Only one bullet."]

    def test_kept_experiences_are_ordered_too(self):
        # KEEP copies the source verbatim, so without the post-pass its bullets
        # would ship in source order.
        resume = make_resume()
        resume.experiences[0] = resume.experiences[0].model_copy(
            update={
                "highlights": [
                    "Attended team meetings.",
                    "Built Python services on AWS.",
                ]
            }
        )
        result, _, _ = _generate([], resume=resume)
        assert result.experiences[0].highlights[0] == "Built Python services on AWS."

    def test_projects_are_ordered_too(self):
        resume = make_resume()
        resume.projects[0] = resume.projects[0].model_copy(
            update={
                "highlights": [
                    "Wrote a README.",
                    "Built a Python CLI on AWS.",
                ]
            }
        )
        result, _, _ = _generate([], resume=resume)
        assert _by_id(result.projects, "proj_001").highlights[0] == (
            "Built a Python CLI on AWS."
        )


class TestQuantifiedOutcomes:
    """
    Aggressive mode asks for at least one number per experience and project.
    A bullet with a figure is the one a reviewer believes.

    Counted, not judged: whether a number is *believable* cannot be checked
    mechanically — "cut latency 40%" and "cut latency 97%" look identical to a
    regular expression — so the prompt carries that rule and this only counts.
    """

    def _plan(self, mode):
        return _rewrite_experience_plan("exp_002", mode=mode)

    def _run(self, mode, highlights):
        return _generate(
            [
                experiences_response(
                    experience_entry("exp_002", highlights=highlights)
                )
            ],
            plan=self._plan(mode),
        )

    def test_a_section_without_a_number_is_reported(self):
        _, generator, _ = self._run(
            "AGGRESSIVE", ["Shipped a payments service."]
        )
        assert any(
            "exp_002" in n and "quantified" in n for n in generator.last_discarded
        )

    def test_a_section_with_a_number_is_not_reported(self):
        _, generator, _ = self._run(
            "AGGRESSIVE", ["Shipped a payments service, cutting latency by 30%."]
        )
        assert not [
            n for n in generator.last_discarded if "exp_002" in n and "quantified" in n
        ]

    def test_one_number_anywhere_in_the_section_is_enough(self):
        _, generator, _ = self._run(
            "AGGRESSIVE",
            ["Owned the payments service.", "Cut latency by 30%."],
        )
        assert not [
            n for n in generator.last_discarded if "exp_002" in n and "quantified" in n
        ]

    def test_projects_are_checked_too(self):
        # make_resume()'s projects carry no numbers.
        _, generator, _ = _generate([])
        # An all-KEEP plan is AGGRESSIVE by default in make_plan().
        assert any(
            "proj_001" in n and "quantified" in n for n in generator.last_discarded
        )

    def test_strict_mode_never_reports_it(self):
        # Strict forbids introducing any number not already in the source, so
        # demanding one would be contradictory.
        _, generator, _ = self._run("STRICT", ["Shipped a payments service."])
        assert not [n for n in generator.last_discarded if "quantified" in n]


class TestCapitalisation:
    """
    Job vocabulary worked into prose comes back Capitalised; the pass
    lowercases it. What the source already capitalised is left alone.
    """

    def _plan(self):
        return make_plan(
            summary_plan={
                "action": "REWRITE",
                "priority": "HIGH",
                "reasoning": "Retarget to the job.",
                "keywords_to_include": [],
            }
        )

    def _summary(self, text, resume=None):
        result, _, _ = _generate(
            [summary_response(text)], plan=self._plan(), resume=resume
        )
        return result.summary

    def test_process_words_are_lowercased(self):
        out = self._summary(
            "Engineer ensuring Code Quality and Production Support. " + "word " * 25
        )
        assert "code quality" in out
        assert "Code Quality" not in out

    def test_the_sources_own_capitalisation_survives(self):
        resume = make_resume()
        resume.summary = "Backend Software Engineer at Acme Corp using Python."
        out = self._summary(
            "Seasoned Backend Software Engineer at Acme Corp. " + "word " * 25,
            resume=resume,
        )
        assert "Backend Software Engineer" in out

    def test_proper_nouns_survive(self):
        out = self._summary(
            "Engineer using Java, Redis and Spring Boot daily. " + "word " * 25
        )
        for name in ("Java", "Redis", "Spring Boot"):
            assert name in out

    def test_highlights_are_cleaned_too(self):
        plan = _rewrite_experience_plan("exp_002")
        result, _, _ = _generate(
            [
                experiences_response(
                    experience_entry(
                        "exp_002",
                        highlights=["Ensured Code Quality across 20 services."],
                    )
                )
            ],
            plan=plan,
        )
        assert result.experiences[1].highlights[0] == (
            "Ensured code quality across 20 services."
        )
