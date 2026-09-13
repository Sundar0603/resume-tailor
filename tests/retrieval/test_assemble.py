"""
Assembling a canonical ``Resume`` from a retrieval result.

The hinge of task 020: the rest of the pipeline keeps speaking ``Resume``, so
the Planner, Generator, Validator and Renderer need no new vocabulary and keep
every guarantee they already hold.
"""

from src.knowledge.models import KnowledgeBase
from src.parser.models import EntitySource
from src.retrieval import KnowledgeBaseRetriever, build_source_resume
from src.retrieval import selection
from src.validation import ResumeValidator

from .conftest import make_backend_job, make_job_analysis, make_knowledge_base


def assemble(knowledge_base=None, job=None):
    knowledge_base = knowledge_base or make_knowledge_base()
    retrieval = KnowledgeBaseRetriever().retrieve(
        knowledge_base, job or make_job_analysis()
    )
    return knowledge_base, retrieval, build_source_resume(knowledge_base, retrieval)


class TestTheResultIsAnOrdinaryResume:
    def test_metadata_comes_from_the_knowledge_base(self):
        knowledge_base, _, resume = assemble()
        assert resume.metadata.template == knowledge_base.metadata.template
        assert resume.metadata.resume == knowledge_base.metadata.knowledge_base

    def test_contact_comes_from_the_knowledge_base(self):
        knowledge_base, _, resume = assemble()
        assert resume.contact == knowledge_base.contact

    def test_the_summary_is_the_selected_variant(self):
        knowledge_base, retrieval, resume = assemble()
        assert resume.summary == knowledge_base.summary(retrieval.summary_id).text

    def test_every_entity_is_canonical(self):
        """
        Nothing assembled from the Knowledge Base may be marked GENERATED.
        ``EntitySource`` is what the Reporter and Revision Engine read to tell
        an invented entity from a verified one.
        """
        _, _, resume = assemble()
        entities = (
            list(resume.skills)
            + list(resume.experiences)
            + list(resume.projects)
            + list(resume.education)
        )
        assert entities
        for entity in entities:
            assert entity.source is EntitySource.CANONICAL


class TestItPassesTheValidator:
    def test_the_assembled_resume_validates_against_itself(self):
        _, _, resume = assemble()
        result = ResumeValidator().validate(
            source_resume=resume, generated_resume=resume, mode="AGGRESSIVE"
        )
        assert result.is_valid, [e.message for e in result.errors]

    def test_it_raises_no_warnings_either(self):
        """
        Not required, but a resume that warns on arrival spends the Revision
        Engine's budget on a problem retrieval created.
        """
        _, _, resume = assemble()
        result = ResumeValidator().validate(
            source_resume=resume, generated_resume=resume, mode="AGGRESSIVE"
        )
        assert [w.code.value for w in result.warnings] == []

    def test_it_meets_the_validator_floors(self):
        _, _, resume = assemble()
        assert resume.total_experiences() == 2
        assert resume.total_projects() >= 2
        assert resume.total_education() >= 1
        assert len(resume.skills) >= 1


class TestExperienceOrderIsPreserved:
    def test_experiences_keep_knowledge_base_order(self):
        """
        Load-bearing: the Validator compares experiences against the source
        *positionally*, and a resume reads reverse-chronologically whatever the
        job wants. Ranking must never reorder them.
        """
        knowledge_base, _, resume = assemble()
        assert [e.id for e in resume.experiences] == [
            e.id for e in knowledge_base.experiences
        ]

    def test_order_holds_for_a_different_job(self):
        knowledge_base, _, resume = assemble(job=make_backend_job())
        assert [e.id for e in resume.experiences] == [
            e.id for e in knowledge_base.experiences
        ]

    def test_education_keeps_knowledge_base_order(self):
        knowledge_base, _, resume = assemble()
        assert [d.id for d in resume.education] == [
            d.id for d in knowledge_base.education
        ]


class TestRelevanceOrderingWhereItIsSafe:
    def test_projects_are_ordered_most_relevant_first(self):
        """
        The Generator sorts by plan priority and the Revision Engine trims from
        the bottom, so the last element must be the one worth giving up.
        """
        _, retrieval, resume = assemble()
        assert [p.id for p in resume.projects] == retrieval.selected_ids("project")

    def test_skill_categories_are_ordered_most_relevant_first(self):
        _, retrieval, resume = assemble()
        assert [c.id for c in resume.skills] == retrieval.selected_ids("skill_category")


class TestKnowledgeBaseIdsAreCarriedThrough:
    def test_project_ids_are_the_knowledge_base_ids(self):
        knowledge_base, _, resume = assemble()
        known = {p.id for p in knowledge_base.projects}
        assert {p.id for p in resume.projects} <= known

    def test_ids_are_not_renumbered_positionally(self):
        """
        A positional renumber would throw away the lineage that lets a finished
        report name the canonical fact a bullet came from.
        """
        _, _, resume = assemble()
        assert [p.id for p in resume.projects] != ["proj_001", "proj_002", "proj_003"]

    def test_ids_remain_unique(self):
        _, _, resume = assemble()
        for group in (resume.skills, resume.experiences, resume.projects, resume.education):
            ids = [entity.id for entity in group]
            assert len(ids) == len(set(ids))


class TestTheKnowledgeBaseIsUnreachable:
    def test_mutating_the_resume_does_not_touch_the_knowledge_base(self):
        """
        "Read-only input" is enforced by unreachability, not by discipline:
        every entity handed over is a deep copy.
        """
        knowledge_base, _, resume = assemble()
        before = knowledge_base.model_dump_json()

        resume.experiences[0].highlights.append("A fabricated bullet.")
        resume.projects[0].name = "Renamed"
        resume.skills[0].skills.clear()
        resume.contact.email = "attacker@example.com"

        assert knowledge_base.model_dump_json() == before

    def test_assembly_itself_mutates_nothing(self):
        knowledge_base = make_knowledge_base()
        before = knowledge_base.model_dump_json()
        retrieval = KnowledgeBaseRetriever().retrieve(knowledge_base, make_job_analysis())
        build_source_resume(knowledge_base, retrieval)
        assert knowledge_base.model_dump_json() == before


class TestTheCrossRoleContentSurvivesAssembly:
    def test_the_ai_project_is_on_the_resume(self):
        _, _, resume = assemble()
        assert any(p.name == "Resume Tailor" for p in resume.projects)

    def test_the_mcp_bullet_is_on_the_resume(self):
        _, _, resume = assemble()
        assert any(
            "MCP layer" in highlight
            for experience in resume.experiences
            for highlight in experience.highlights
        )

    def test_the_resume_holds_facts_from_several_role_specific_resumes(self):
        """
        The thing no single ``content/*.md`` can do: one resume carrying the
        AI work, the frontend work and the backend work at once.
        """
        _, _, resume = assemble()
        bullets = " ".join(
            h for e in resume.experiences for h in e.highlights
        )
        assert "MCP layer" in bullets          # cybersecurity-ai only
        assert "Vue.js component libraries" in bullets  # fullstack only


class TestBudgetsAreRespected:
    def test_no_experience_exceeds_its_budget(self):
        _, _, resume = assemble()
        assert len(resume.experiences[0].highlights) <= selection.FULL_TIME_HIGHLIGHTS
        assert len(resume.experiences[1].highlights) <= selection.INTERNSHIP_HIGHLIGHTS

    def test_no_project_exceeds_its_budget(self):
        _, _, resume = assemble()
        for project in resume.projects:
            assert len(project.highlights) <= selection.MAX_PROJECT_HIGHLIGHTS

    def test_no_entity_arrives_with_an_empty_bullet_list(self):
        """
        An empty ``itemize`` is a LaTeX error, not an empty list
        (PROJECT_KNOWLEDGE §10d), and the Validator requires non-empty
        highlights.
        """
        _, _, resume = assemble()
        for entity in list(resume.experiences) + list(resume.projects):
            assert entity.highlights
