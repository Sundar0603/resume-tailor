"""
The Knowledge Base must not have lost anything on the way in.

Task 020 §27: "Do not lose any canonical information during migration." These
tests read the **real** ``content/*.md`` and the **real**
``knowledge/knowledge_base.md`` off disk, following the precedent set by
``tests/content/`` — a factory fixture cannot catch a fact that never made it
into the file.

Two deliberate divergences.

The contact email: the four resumes disagree (``sundars0603@`` on backend and
fullstack, ``sundarselvam3@`` on the two cybersecurity variants) and the
Knowledge Base has to carry one, so the chosen address is asserted directly
rather than compared.

Skill *naming variants*: two resumes list ``Vue`` and one lists ``Vue.js``, and
carrying both meant one resume could ship the same skill twice. Coverage is
therefore checked through the alias map, so ``Vue`` counts as present when
``Vue.js`` is. This is not a weakening — a genuinely absent skill still fails,
which ``TestTheAliasRuleStillCatchesRealLoss`` proves by removing one.
"""

from pathlib import Path

import pytest

from src.knowledge import KnowledgeBaseParser
from src.parser import ResumeParser
from src.retrieval.aliases import expand
from src.vocabulary import normalise

CONTENT_DIRECTORY = Path("content")
KNOWLEDGE_BASE = Path("knowledge/knowledge_base.md")

#: Decided with the user: the Knowledge Base's canonical address.
CANONICAL_EMAIL = "sundarselvam3@gmail.com"


@pytest.fixture(scope="module")
def knowledge_base():
    return KnowledgeBaseParser().parse(str(KNOWLEDGE_BASE))


@pytest.fixture(scope="module")
def source_resumes():
    parser = ResumeParser()
    return {
        path.name: parser.parse(str(path))
        for path in sorted(CONTENT_DIRECTORY.glob("*.md"))
    }


def _normalised(values):
    return {normalise(value) for value in values if normalise(value)}


class TestTheFixturesAreNotVacuous:
    """
    Guards against a green-but-meaningless suite.

    ``tests/content/test_content_links.py`` carries the same pair, for the same
    reason: every assertion below is "for each X in the source, X is in the KB",
    which passes trivially when the source is empty.
    """

    def test_the_knowledge_base_exists(self):
        assert KNOWLEDGE_BASE.is_file()

    def test_all_four_resumes_were_found(self, source_resumes):
        assert len(source_resumes) == 4

    def test_the_knowledge_base_is_not_empty(self, knowledge_base):
        assert knowledge_base.experiences
        assert knowledge_base.projects
        assert knowledge_base.skills
        assert knowledge_base.education
        assert knowledge_base.summaries


class TestNoHighlightWasLost:
    def test_every_experience_highlight_survives(self, knowledge_base, source_resumes):
        pool = _normalised(
            h for e in knowledge_base.experiences for h in e.highlights
        )
        for name, resume in source_resumes.items():
            for experience in resume.experiences:
                for highlight in experience.highlights:
                    assert normalise(highlight) in pool, (name, highlight[:60])

    def test_every_project_highlight_survives(self, knowledge_base, source_resumes):
        pool = _normalised(h for p in knowledge_base.projects for h in p.highlights)
        for name, resume in source_resumes.items():
            for project in resume.projects:
                for highlight in project.highlights:
                    assert normalise(highlight) in pool, (name, highlight[:60])

    def test_the_pool_is_bigger_than_any_single_resume(self, knowledge_base, source_resumes):
        """
        The point of the whole task: the Knowledge Base holds more than any one
        view. If this ever reads equal, the merge collapsed to a single resume.
        """
        pool = len([h for e in knowledge_base.experiences for h in e.highlights])
        for resume in source_resumes.values():
            largest = sum(len(e.highlights) for e in resume.experiences)
            assert pool > largest


def _covered(skills):
    """Return every name under which the Knowledge Base carries these skills."""
    covered = set()
    for skill in skills:
        covered |= expand(skill)
    return covered


class TestNoSkillWasLost:
    def test_every_skill_survives(self, knowledge_base, source_resumes):
        pool = _covered(knowledge_base.as_resume().all_skills())
        for name, resume in source_resumes.items():
            for skill in resume.all_skills():
                assert expand(skill) & pool, (name, skill)

    def test_every_skill_category_survives(self, knowledge_base, source_resumes):
        pool = _normalised(c.category for c in knowledge_base.skills)
        for name, resume in source_resumes.items():
            for category in resume.skills:
                assert normalise(category.category) in pool, (name, category.category)


class TestNoTechnologyOrDomainWasLost:
    def test_every_experience_technology_and_domain_survives(
        self, knowledge_base, source_resumes
    ):
        technologies = _normalised(
            t for e in knowledge_base.experiences for t in e.technologies
        )
        domains = _normalised(d for e in knowledge_base.experiences for d in e.domains)
        for name, resume in source_resumes.items():
            for experience in resume.experiences:
                for term in experience.technologies:
                    assert normalise(term) in technologies, (name, term)
                for term in experience.domains:
                    assert normalise(term) in domains, (name, term)

    def test_every_project_technology_and_domain_survives(
        self, knowledge_base, source_resumes
    ):
        technologies = _normalised(
            t for p in knowledge_base.projects for t in p.technologies
        )
        domains = _normalised(d for p in knowledge_base.projects for d in p.domains)
        for name, resume in source_resumes.items():
            for project in resume.projects:
                for term in project.technologies:
                    assert normalise(term) in technologies, (name, term)
                for term in project.domains:
                    assert normalise(term) in domains, (name, term)


class TestNoEntityWasLost:
    def test_every_project_survives_by_name(self, knowledge_base, source_resumes):
        names = _normalised(p.name for p in knowledge_base.projects)
        for name, resume in source_resumes.items():
            for project in resume.projects:
                assert normalise(project.name) in names, (name, project.name)

    def test_every_experience_survives_by_company_and_role(
        self, knowledge_base, source_resumes
    ):
        pairs = {
            (normalise(e.company), normalise(e.role))
            for e in knowledge_base.experiences
        }
        for name, resume in source_resumes.items():
            for experience in resume.experiences:
                key = (normalise(experience.company), normalise(experience.role))
                assert key in pairs, (name, key)

    def test_every_degree_survives(self, knowledge_base, source_resumes):
        pairs = {
            (normalise(d.institution), normalise(d.degree))
            for d in knowledge_base.education
        }
        for name, resume in source_resumes.items():
            for degree in resume.education:
                assert (normalise(degree.institution), normalise(degree.degree)) in pairs

    def test_every_summary_survives(self, knowledge_base, source_resumes):
        pool = _normalised(s.text for s in knowledge_base.summaries)
        for name, resume in source_resumes.items():
            assert normalise(resume.summary) in pool, name


class TestTheCrossRoleGapIsClosed:
    """
    The motivating case, asserted rather than described.

    These facts exist in exactly one resume today, which is why a job
    description matched against any other one cannot reach them.
    """

    def test_the_resume_tailor_project_is_canonical(self, knowledge_base, source_resumes):
        owners = [
            name
            for name, resume in source_resumes.items()
            if any(normalise(p.name) == "resume tailor" for p in resume.projects)
        ]
        assert owners == ["cybersecurity_ai_resume.md"]
        assert any(normalise(p.name) == "resume tailor" for p in knowledge_base.projects)

    def test_the_mcp_work_is_canonical(self, knowledge_base, source_resumes):
        def mentions_mcp(resume):
            return any(
                "mcp layer" in normalise(h)
                for e in resume.experiences
                for h in e.highlights
            )

        owners = [name for name, r in source_resumes.items() if mentions_mcp(r)]
        assert owners == ["cybersecurity_ai_resume.md"]
        assert any(
            "mcp layer" in normalise(h)
            for e in knowledge_base.experiences
            for h in e.highlights
        )

    def test_the_fullstack_resume_cannot_reach_either(self, source_resumes):
        """The gap this task exists to close, stated as a fact about today."""
        fullstack = source_resumes["fullstack_resume.md"]
        assert not any(normalise(p.name) == "resume tailor" for p in fullstack.projects)
        assert not any(
            "mcp" in normalise(h) for e in fullstack.experiences for h in e.highlights
        )


class TestContact:
    def test_the_canonical_email_is_used(self, knowledge_base):
        assert knowledge_base.contact.email == CANONICAL_EMAIL

    def test_every_other_contact_field_matches_the_sources(
        self, knowledge_base, source_resumes
    ):
        for name, resume in source_resumes.items():
            for field in ("name", "phone", "linkedin", "github"):
                assert getattr(knowledge_base.contact, field) == getattr(
                    resume.contact, field
                ), (name, field)


class TestTheAliasRuleStillCatchesRealLoss:
    """
    Allowing a naming variant must not become allowing anything.

    ``test_every_skill_survives`` compares through the alias map so ``Vue``
    counts as covered by ``Vue.js``. That is only safe if a skill with no
    canonical equivalent in the Knowledge Base still fails, so it is checked
    here directly rather than assumed.
    """

    def test_a_naming_variant_counts_as_covered(self):
        assert expand("Vue") & _covered(["Vue.js", "Pinia"])

    def test_an_unrelated_skill_does_not(self):
        assert not (expand("Kubernetes") & _covered(["Vue.js", "Pinia"]))

    def test_a_removed_skill_is_caught(self, knowledge_base, source_resumes):
        """Drop a real skill from the pool and the rule must reject it."""
        remaining = [
            skill
            for skill in knowledge_base.as_resume().all_skills()
            if normalise(skill) != "pinia"
        ]
        assert not (expand("Pinia") & _covered(remaining))

    def test_vue_is_carried_under_its_canonical_name_only(self, knowledge_base):
        frontend = knowledge_base.skill_category("skill_005")
        assert "Vue.js" in frontend.skills
        assert "Vue" not in frontend.skills
