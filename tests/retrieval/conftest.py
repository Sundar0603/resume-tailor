"""
Fixtures for the retrieval suite.

Builds a Knowledge Base whose shape reproduces the real one's defining
property: facts that exist in only one of the four role-specific resumes. The
AI project and the MCP bullet are exactly that, and they are what the
cross-role tests reach for.
"""

import pytest

from src.analyzer.models import JobAnalysis
from src.knowledge import KnowledgeBaseParser
from src.knowledge.models import (
    CanonicalSummary,
    KnowledgeBase,
    KnowledgeMetadata,
)
from src.parser.models import Contact, Education, Experience, Project, SkillCategory

REAL_KNOWLEDGE_BASE = "knowledge/knowledge_base.md"


def make_contact() -> Contact:
    return Contact(
        name="Sundar S",
        phone="+91 7397398343",
        email="sundarselvam3@gmail.com",
        linkedin="https://www.linkedin.com/in/sundar-s-870042235/",
        github="https://github.com/Sundar0603",
    )


def make_knowledge_base(**overrides) -> KnowledgeBase:
    """Return a Knowledge Base with the cross-role gap built in."""
    data = dict(
        metadata=KnowledgeMetadata(
            knowledge_base="test", template="default", version="1.0"
        ),
        contact=make_contact(),
        summaries=[
            CanonicalSummary(
                id="sum_001",
                label="backend emphasis",
                text=(
                    "Backend Software Engineer with two years at Zoho building "
                    "enterprise-scale Security Operations Center platforms using Java, "
                    "Spring Boot, Redis and MySQL. Experienced in designing distributed "
                    "workflows and delivering scalable backend services that support "
                    "security investigations and automated incident management."
                ),
            ),
            CanonicalSummary(
                id="sum_002",
                label="AI emphasis",
                text=(
                    "Full Stack Software Engineer with two years at Zoho building "
                    "AI-assisted platforms in Python, FastAPI and PostgreSQL alongside "
                    "Java and Vue.js. Experienced in LLM agent orchestration, REST API "
                    "design and workflow automation for security investigation tooling."
                ),
            ),
        ],
        skills=[
            SkillCategory(id="skill_001", category="Backend", skills=["Spring Boot", "Redis", "MySQL"]),
            SkillCategory(id="skill_002", category="AI and Agentic Systems", skills=["LLM", "MCP", "OpenAI APIs"]),
            SkillCategory(id="skill_003", category="Frontend", skills=["Vue.js", "Pinia"]),
            SkillCategory(id="skill_004", category="Security", skills=["SIEM", "Threat Intelligence"]),
            SkillCategory(id="skill_005", category="Languages", skills=["Python", "Java"]),
            SkillCategory(id="skill_006", category="Tools", skills=["Git", "Docker"]),
            SkillCategory(id="skill_007", category="Databases", skills=["PostgreSQL"]),
        ],
        experiences=[
            Experience(
                id="exp_001",
                company="Zoho Corporation",
                role="Software Developer",
                employment_type="Full Time",
                location="Chennai",
                duration="May 2024 - Present",
                technologies=["Java", "Spring Boot", "Redis", "Vue.js", "Python"],
                domains=["SOC Platforms", "AI Agents", "Caching"],
                highlights=[
                    # Only ever on the cybersecurity-AI resume.
                    "Built the MCP layer for an internal security platform, exposing REST APIs as model-invocable tools for an LLM agent.",
                    # Only ever on the fullstack resume.
                    "Built and maintained reusable Vue.js component libraries and reactive Pinia state management.",
                    # Only ever on the backend resume.
                    "Implemented Redis-backed API rate limiting to safeguard infrastructure against flood attacks.",
                    # Two phrasings of one fact, from two different resumes.
                    "Developed a rule management platform for creating, validating, versioning, and deploying event-processing rules powering automated ticket generation workflows.",
                    "Developed a rule management platform enabling users to create, edit, validate, and manage event-processing rules used for automated ticket generation and workflow automation.",
                    "Designed threat intelligence ingestion pipelines normalising indicators into a central repository.",
                    "Engineered high-performance SOC queries with strict time-partitioning, cutting execution delays by 70%.",
                ],
            ),
            Experience(
                id="exp_002",
                company="Zoho Corporation",
                role="Software Developer Intern",
                employment_type="Internship",
                location="Chennai",
                duration="Dec 2023 - Apr 2024",
                technologies=["Java", "Spring Boot"],
                domains=["SOC", "Deployment"],
                highlights=[
                    "Implemented Service Worker-based request interception and proxying mechanisms.",
                    "Implemented data retention policies for high-volume enterprise workflow platforms.",
                    "Managed application deployments across multiple data centers.",
                    "Contributed to incident management workflows for SOC operations and incident response.",
                ],
            ),
        ],
        projects=[
            Project(
                id="proj_001",
                name="SOCrates",
                type="Personal",
                technologies=["Python", "OpenAI APIs"],
                domains=["SOC Automation"],
                highlights=["Built automated investigation pipelines reducing response time by 40%."],
            ),
            Project(
                id="proj_002",
                name="Firewall Analyser",
                type="Personal",
                technologies=["Java", "MySQL"],
                domains=["Firewall Systems"],
                highlights=["Scored firewall rules for risk across a large estate."],
            ),
            Project(
                id="proj_003",
                name="Resume Tailor",
                type="Personal",
                repository="https://github.com/Sundar0603/resume-tailor",
                technologies=["Python", "FastAPI", "LLM", "PostgreSQL"],
                domains=["AI Agents", "Workflow Automation"],
                highlights=["Built an LLM pipeline that tailors resumes to a job description."],
            ),
            Project(
                id="proj_004",
                name="Study Tracker",
                type="Personal",
                technologies=["Vue 3", "MySQL"],
                domains=["Productivity"],
                highlights=["Tracked daily study hours with charts and streaks."],
            ),
        ],
        education=[
            Education(
                id="edu_001",
                institution="Velammal Engineering College",
                degree="Bachelor of Engineering",
                major="Computer Science and Engineering",
                duration="2020 - 2024",
                cgpa="9.18",
                location="Chennai",
            )
        ],
    )
    data.update(overrides)
    return KnowledgeBase(**data)


def make_job_analysis(**overrides) -> JobAnalysis:
    """A Full Stack + AI job: the pairing task 020 §17 is written around."""
    data = dict(
        role="Full Stack Engineer, AI Platform",
        required_skills=["Python", "FastAPI", "REST APIs", "PostgreSQL"],
        preferred_skills=["Large Language Models"],
        technologies=["Python", "FastAPI", "PostgreSQL", "LLM"],
        domains=["AI Agents", "Workflow Automation"],
        responsibilities=["Build AI-powered features end to end"],
        qualifications=[],
        nice_to_have=[],
        keywords=["AI", "LLM", "REST"],
    )
    data.update(overrides)
    return JobAnalysis(**data)


def make_backend_job(**overrides) -> JobAnalysis:
    """A job with no AI signal at all, for contrast."""
    data = dict(
        role="Backend Engineer",
        required_skills=["Java", "Spring Boot", "MySQL"],
        preferred_skills=[],
        technologies=["Java", "Spring Boot", "Redis", "MySQL"],
        domains=["Caching"],
        responsibilities=["Maintain high-throughput backend services"],
        qualifications=[],
        nice_to_have=[],
        keywords=["Java", "backend"],
    )
    data.update(overrides)
    return JobAnalysis(**data)


@pytest.fixture
def knowledge_base():
    return make_knowledge_base()


@pytest.fixture
def job_analysis():
    return make_job_analysis()


@pytest.fixture
def backend_job():
    return make_backend_job()


@pytest.fixture(scope="module")
def real_knowledge_base():
    """The Knowledge Base actually on disk."""
    return KnowledgeBaseParser().parse(REAL_KNOWLEDGE_BASE)
