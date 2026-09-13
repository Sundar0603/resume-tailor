"""
The motivating case, against the Knowledge Base that is actually on disk.

``tests/retrieval/test_retriever.py`` proves the mechanism on a fixture. This
proves it on the real data, which is the only thing that establishes the task
actually delivered anything: a fixture built to demonstrate cross-role
retrieval will always demonstrate it.

The claim under test, from task 020 §17:

    The system must not conclude that Project A is unavailable merely because
    it wasn't present in the Full Stack resume.
"""

import pytest

from src.analyzer.models import JobAnalysis
from src.parser import ResumeParser
from src.retrieval import KnowledgeBaseRetriever, build_source_resume
from src.vocabulary import normalise

FULLSTACK_RESUME = "content/fullstack_resume.md"


def fullstack_ai_job() -> JobAnalysis:
    """A Full Stack role that also wants AI work — the §17 pairing."""
    return JobAnalysis(
        role="Full Stack Engineer, AI Platform",
        required_skills=["Python", "FastAPI", "REST APIs", "PostgreSQL", "Vue.js"],
        preferred_skills=["Large Language Models", "Model Context Protocol"],
        technologies=["Python", "FastAPI", "PostgreSQL", "LLM", "Docker"],
        domains=["AI Agents", "Workflow Automation", "Full Stack Development"],
        responsibilities=[
            "Build AI-powered product features end to end",
            "Design and ship REST APIs backed by relational storage",
        ],
        qualifications=[],
        nice_to_have=[],
        keywords=["AI", "agents", "LLM", "full stack", "REST"],
    )


@pytest.fixture(scope="module")
def fullstack_resume():
    return ResumeParser().parse(FULLSTACK_RESUME)


@pytest.fixture(scope="module")
def retrieval(real_knowledge_base):
    return KnowledgeBaseRetriever().retrieve(real_knowledge_base, fullstack_ai_job())


@pytest.fixture(scope="module")
def assembled(real_knowledge_base, retrieval):
    return build_source_resume(real_knowledge_base, retrieval)


class TestTheGapIsRealBeforeTheFix:
    """
    Establishes the premise. Without these the tests below could pass on a
    resume that already contained the content.
    """

    def test_the_fullstack_resume_has_no_ai_project(self, fullstack_resume):
        assert not any(
            normalise(p.name) == "resume tailor" for p in fullstack_resume.projects
        )

    def test_the_fullstack_resume_has_no_mcp_work(self, fullstack_resume):
        assert not any(
            "mcp" in normalise(h)
            for e in fullstack_resume.experiences
            for h in e.highlights
        )


class TestTheGapIsClosedAfterIt:
    def test_the_ai_project_is_retrieved(self, retrieval, real_knowledge_base):
        names = {
            real_knowledge_base.project(pid).name
            for pid in retrieval.selected_ids("project")
        }
        assert "Resume Tailor" in names

    def test_the_ai_project_reaches_the_assembled_resume(self, assembled):
        assert any(p.name == "Resume Tailor" for p in assembled.projects)

    def test_the_mcp_work_reaches_the_assembled_resume(self, assembled):
        assert any(
            "mcp layer" in normalise(h)
            for e in assembled.experiences
            for h in e.highlights
        )

    def test_the_mcp_bullet_is_the_strongest_match(self, retrieval):
        """Not merely included — it is what the job most wants."""
        ranked = sorted(
            [h for h in retrieval.highlights if h.entity_id == "exp_001"],
            key=lambda h: -h.score,
        )
        assert "mcp layer" in normalise(ranked[0].text)


class TestTheResumeSpansAllFourSourceResumes:
    """
    The property no single ``content/*.md`` has: one resume carrying the AI
    work, the frontend work and the backend work at once.
    """

    def test_it_carries_content_unique_to_the_ai_resume(self, assembled):
        bullets = " ".join(
            normalise(h) for e in assembled.experiences for h in e.highlights
        )
        assert "mcp layer" in bullets

    def test_it_carries_content_unique_to_the_fullstack_resume(self, assembled):
        bullets = " ".join(
            normalise(h) for e in assembled.experiences for h in e.highlights
        )
        assert "vue.js component libraries" in bullets

    def test_no_source_resume_contains_both(self):
        """
        Proves the combination is genuinely new rather than copied from one
        file that happened to have both.
        """
        from pathlib import Path

        parser = ResumeParser()
        for path in sorted(Path("content").glob("*.md")):
            resume = parser.parse(str(path))
            bullets = " ".join(
                normalise(h) for e in resume.experiences for h in e.highlights
            )
            assert not (
                "mcp layer" in bullets and "vue.js component libraries" in bullets
            ), path.name


class TestTheRunIsStillValid:
    def test_the_assembled_resume_passes_the_validator(self, assembled):
        from src.validation import ResumeValidator

        result = ResumeValidator().validate(
            source_resume=assembled, generated_resume=assembled, mode="AGGRESSIVE"
        )
        assert result.is_valid, [e.message for e in result.errors]

    def test_no_duplicate_phrasing_ships(self, retrieval):
        selected = retrieval.selected_highlights("exp_001")
        from src.retrieval.selection import DUPLICATE_THRESHOLD, overlap

        for index, first in enumerate(selected):
            for second in selected[index + 1 :]:
                assert overlap(first, second) < DUPLICATE_THRESHOLD

    def test_retrieval_is_deterministic_on_the_real_data(self, real_knowledge_base):
        first = KnowledgeBaseRetriever().retrieve(real_knowledge_base, fullstack_ai_job())
        second = KnowledgeBaseRetriever().retrieve(real_knowledge_base, fullstack_ai_job())
        assert first == second
