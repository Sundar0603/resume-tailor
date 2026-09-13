"""
Knowledge Base retrieval.

The suite task 020 §28 asks for: relevant entities are found regardless of
which role-specific resume happened to contain them, the result is
deterministic, and the Retriever does only retrieval.
"""

import pytest

from src.knowledge.models import KnowledgeBase
from src.retrieval import (
    EmptyKnowledgeBase,
    InsufficientCanonicalData,
    KnowledgeBaseRetriever,
)
from src.retrieval import selection

from .conftest import make_backend_job, make_job_analysis, make_knowledge_base


def retrieve(knowledge_base=None, job=None):
    return KnowledgeBaseRetriever().retrieve(
        knowledge_base or make_knowledge_base(), job or make_job_analysis()
    )


class TestTheCrossRoleCase:
    """
    Task 020 §17, asserted.

    The AI project and the MCP bullet live in exactly one of the four
    role-specific resumes. A Full Stack + AI job must reach both, and the
    reason it now can is that retrieval reads the Knowledge Base rather than a
    file someone picked.
    """

    def test_the_ai_project_is_retrieved(self):
        result = retrieve()
        assert "proj_003" in result.selected_ids("project")

    def test_the_ai_project_outranks_everything_else(self):
        result = retrieve()
        assert result.projects[0].id == "proj_003"

    def test_the_mcp_highlight_is_selected(self):
        result = retrieve()
        selected = result.selected_highlights("exp_001")
        assert any("MCP layer" in text for text in selected)

    def test_the_mcp_highlight_outranks_the_rest(self):
        result = retrieve()
        ranked = sorted(
            [h for h in result.highlights if h.entity_id == "exp_001"],
            key=lambda h: -h.score,
        )
        assert "MCP layer" in ranked[0].text

    def test_a_backend_job_does_not_reach_for_it(self):
        """
        The other half of the claim: retrieval discriminates.

        If the AI project were selected for every job, "it was retrieved" would
        mean nothing.
        """
        result = retrieve(job=make_backend_job())
        assert "proj_003" not in result.selected_ids("project")

    def test_the_two_jobs_select_differently(self):
        ai = retrieve().selected_ids("project")
        backend = retrieve(job=make_backend_job()).selected_ids("project")
        assert ai != backend


class TestSummaryVariants:
    def test_the_best_matching_variant_is_chosen(self):
        assert retrieve().summary_id == "sum_002"

    def test_a_different_job_chooses_a_different_variant(self):
        assert retrieve(job=make_backend_job()).summary_id == "sum_001"

    def test_exactly_one_summary_is_selected(self):
        result = retrieve()
        assert len([s for s in result.summaries if s.selected]) == 1

    def test_every_variant_is_still_reported(self):
        result = retrieve()
        assert len(result.summaries) == 2


class TestSelectionBudgets:
    def test_projects_are_capped(self):
        result = retrieve()
        assert len(result.selected_ids("project")) == selection.MAX_PROJECTS

    def test_skill_categories_are_capped(self):
        result = retrieve()
        assert len(result.selected_ids("skill_category")) == selection.MAX_SKILL_CATEGORIES

    def test_a_full_time_experience_is_trimmed_to_its_budget(self):
        result = retrieve()
        assert len(result.selected_highlights("exp_001")) == selection.FULL_TIME_HIGHLIGHTS

    def test_an_internship_is_trimmed_to_its_own_budget(self):
        result = retrieve()
        assert len(result.selected_highlights("exp_002")) == selection.INTERNSHIP_HIGHLIGHTS

    def test_every_experience_is_always_selected(self):
        """
        The Planner cannot add or remove an experience and the Validator
        requires exactly two, so ranking them explains rather than decides.
        """
        result = retrieve()
        assert all(e.selected for e in result.experiences)

    def test_every_degree_is_always_selected(self):
        assert all(d.selected for d in retrieve().education)

    def test_an_unselected_project_contributes_no_highlights(self):
        result = retrieve()
        unselected = [p.id for p in result.projects if not p.selected]
        assert unselected
        for project_id in unselected:
            assert result.selected_highlights(project_id) == []


class TestTheDuplicateGuard:
    def test_the_two_rule_management_phrasings_never_both_ship(self):
        """
        The pair this guard was measured against. Both are canonical, both stay
        in the Knowledge Base, and shipping both on one resume reads as padding.
        """
        selected = retrieve().selected_highlights("exp_001")
        rule_bullets = [t for t in selected if "rule management platform" in t]
        assert len(rule_bullets) <= 1

    def test_the_dropped_phrasing_is_recorded_as_a_duplicate(self):
        dropped = retrieve().duplicates_dropped()
        assert any("rule management platform" in h.text for h in dropped)

    def test_a_duplicate_names_what_it_restates(self):
        for highlight in retrieve().duplicates_dropped():
            assert highlight.duplicate_of
            assert highlight.duplicate_of != highlight.id

    def test_a_duplicate_does_not_consume_the_budget(self):
        """
        Skipping rather than stopping is what makes "keep every variant"
        workable: the next genuinely different fact moves into the freed slot.
        """
        result = retrieve()
        assert len(result.selected_highlights("exp_001")) == selection.FULL_TIME_HIGHLIGHTS


class TestEverythingIsReported:
    def test_unselected_entities_are_still_scored(self):
        result = retrieve()
        passed_over = result.considered_but_not_selected("project")
        assert passed_over
        assert all(p.score >= 0.0 for p in passed_over)

    def test_matched_terms_explain_a_selection(self):
        result = retrieve()
        ai_project = [p for p in result.projects if p.id == "proj_003"][0]
        assert "llm" in ai_project.matched_terms
        assert "python" in ai_project.matched_terms

    def test_supporting_evidence_is_written(self):
        assert retrieve().supporting_evidence

    def test_evidence_records_what_was_passed_over(self):
        notes = " ".join(retrieve().supporting_evidence)
        assert "did not select" in notes


class TestDeterminism:
    def test_two_retrievals_are_equal(self):
        assert retrieve() == retrieve()

    def test_two_retrievals_serialise_identically(self):
        assert retrieve().model_dump_json() == retrieve().model_dump_json()

    def test_matched_terms_are_ordered_not_set_ordered(self):
        first = [p.matched_terms for p in retrieve().projects]
        second = [p.matched_terms for p in retrieve().projects]
        assert first == second

    def test_equal_scores_break_ties_on_id(self):
        """
        Two entities scoring the same must always come back in the same order,
        or the same inputs could produce a different resume.
        """
        knowledge_base = make_knowledge_base()
        # Both the category name and its skills are scored, so neutralising
        # only one of them leaves a real ranking and never reaches the
        # tie-break this test exists for.
        for index, category in enumerate(knowledge_base.skills):
            category.category = "Neutral {0}".format(index)
            category.skills = ["Widget"]

        ranked = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())

        assert {c.score for c in ranked.skill_categories} == {0.0}
        ids = [c.id for c in ranked.skill_categories]
        assert ids == sorted(ids)


class TestGuards:
    def test_an_empty_knowledge_base_raises(self):
        empty = make_knowledge_base(
            skills=[], experiences=[], projects=[], education=[], summaries=[]
        )
        with pytest.raises(EmptyKnowledgeBase):
            retrieve(knowledge_base=empty)

    def test_too_few_projects_raises(self):
        sparse = make_knowledge_base()
        sparse.projects = sparse.projects[:1]
        with pytest.raises(InsufficientCanonicalData):
            retrieve(knowledge_base=sparse)

    def test_no_summary_raises(self):
        sparse = make_knowledge_base()
        sparse.summaries = []
        with pytest.raises(InsufficientCanonicalData):
            retrieve(knowledge_base=sparse)

    def test_no_education_raises(self):
        sparse = make_knowledge_base()
        sparse.education = []
        with pytest.raises(InsufficientCanonicalData):
            retrieve(knowledge_base=sparse)


class TestTheKnowledgeBaseIsNotMutated:
    def test_retrieval_leaves_the_knowledge_base_equal(self):
        knowledge_base = make_knowledge_base()
        before = knowledge_base.model_dump_json()
        KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert knowledge_base.model_dump_json() == before

    def test_the_pool_is_not_trimmed_in_place(self):
        knowledge_base = make_knowledge_base()
        pool = len(knowledge_base.experiences[0].highlights)
        KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert len(knowledge_base.experiences[0].highlights) == pool


class TestRedundantSkillCategoriesAreSkipped:
    """
    The Knowledge Base is a *merge* of four resumes that each named their own
    categories, so it holds overlapping ones. Printing two headings where one
    is a subset of the other reads as padding, and dropping the subsumed one
    loses no fact — every skill in it is already on the page.
    """

    def test_a_subset_category_is_not_selected(self):
        knowledge_base = make_knowledge_base()
        # "AI tooling" holds nothing "AI and Agentic Systems" does not.
        knowledge_base.skills.append(
            knowledge_base.skills[0].model_copy(
                update={"id": "skill_008", "category": "AI tooling", "skills": ["LLM", "MCP"]}
            )
        )
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        selected = result.selected_ids("skill_category")
        assert "skill_002" in selected      # AI and Agentic Systems
        assert "skill_008" not in selected  # its subset

    def test_the_skip_is_explained(self):
        knowledge_base = make_knowledge_base()
        knowledge_base.skills.append(
            knowledge_base.skills[0].model_copy(
                update={"id": "skill_008", "category": "AI tooling", "skills": ["LLM", "MCP"]}
            )
        )
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        notes = " ".join(result.supporting_evidence)
        assert "skipped skill category skill_008" in notes

    def test_a_skip_does_not_consume_the_budget(self):
        """The next genuinely different category moves into the freed slot."""
        knowledge_base = make_knowledge_base()
        knowledge_base.skills.append(
            knowledge_base.skills[0].model_copy(
                update={"id": "skill_008", "category": "AI tooling", "skills": ["LLM", "MCP"]}
            )
        )
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert (
            len(result.selected_ids("skill_category"))
            == selection.MAX_SKILL_CATEGORIES
        )

    def test_a_partially_overlapping_category_survives(self):
        """
        Only near-total containment is redundant. A category sharing one skill
        with another still carries its own, and must not be dropped.
        """
        knowledge_base = make_knowledge_base()
        knowledge_base.skills.append(
            knowledge_base.skills[0].model_copy(
                update={
                    "id": "skill_008",
                    "category": "Data",
                    "skills": ["LLM", "Kafka", "Spark", "Airflow"],
                }
            )
        )
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert "skill_008" in result.selected_ids("skill_category")

    def test_aliases_count_as_coverage(self):
        """A category listing Vue is covered by one listing Vue.js."""
        from src.retrieval.selection import expanded_skills, is_subsumed

        assert is_subsumed(["Vue"], expanded_skills(["Vue.js", "Pinia"]))

    def test_the_first_category_is_never_skipped(self):
        """There is nothing ahead of it for it to be redundant against."""
        knowledge_base = make_knowledge_base()
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert result.skill_categories[0].selected

    def test_at_least_one_category_always_survives(self):
        """The Validator requires one, whatever the overlaps look like."""
        knowledge_base = make_knowledge_base()
        for category in knowledge_base.skills:
            category.skills = ["Python"]
        result = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        assert len(result.selected_ids("skill_category")) >= 1
