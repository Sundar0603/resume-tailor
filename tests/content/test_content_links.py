"""
Every repository link in the source resumes belongs to the project it sits on.

A wrong URL here is invisible to the rest of the suite. The parser accepts any
string, the renderer faithfully wraps it in ``\\href``, and the compiler is
happy to typeset it, so a link pointing at the wrong repository ships in a PDF
with every stage reporting success. It happened: **Triage Studio** carried
``github.com/Sundar0603/Daily-Studies``, an unrelated Vue/Spring study tracker,
in all four source resumes from the first commit onward.

These checks hold the hand-maintained data to the invariant no downstream stage
can: a link must be evidently about the project that owns it.
"""

import pytest

from src.renderer import LatexRenderer

from .conftest import (
    content_files,
    linked_projects,
    load_resume,
    project_link_targets,
    repository_slug,
    significant_tokens,
    slug_matches_name,
)

#: The exact defect these tests were written for, pinned by name.
_WRONG_TRIAGE_STUDIO_REPOSITORY = "Daily-Studies"


class TestTheContentFilesAreReadable:
    def test_at_least_one_source_resume_exists(self):
        # Guards every other test in this module against passing vacuously
        # because the glob silently matched nothing.
        assert content_files()

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_each_source_resume_parses(self, path):
        resume = load_resume(path)
        assert resume.projects


class TestRepositoryLinksBelongToTheirProject:
    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_every_repository_slug_matches_its_project_name(self, path):
        mismatched = [
            (project.name, project.repository)
            for project in linked_projects(load_resume(path))
            if not slug_matches_name(project.repository, project.name)
        ]
        assert mismatched == [], (
            "{}: repository link does not belong to its project: {}".format(
                path.name, mismatched
            )
        )

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_no_two_projects_share_a_repository(self, path):
        projects = linked_projects(load_resume(path))
        urls = [project.repository for project in projects]
        assert len(urls) == len(set(urls)), (
            "{}: one repository URL is claimed by two projects: {}".format(
                path.name, urls
            )
        )

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_every_repository_is_an_absolute_https_url(self, path):
        for project in linked_projects(load_resume(path)):
            assert project.repository.startswith("https://"), (
                "{}: {} has a non-absolute repository URL: {}".format(
                    path.name, project.name, project.repository
                )
            )

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_no_repository_url_has_trailing_whitespace(self, path):
        for project in linked_projects(load_resume(path)):
            assert project.repository == project.repository.strip()


class TestTheTriageStudioRegression:
    """The specific bug, pinned so it cannot return quietly."""

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_no_project_links_to_the_daily_studies_repository(self, path):
        for project in load_resume(path).projects:
            assert _WRONG_TRIAGE_STUDIO_REPOSITORY not in (project.repository or "")

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_triage_studio_carries_no_foreign_link(self, path):
        for project in load_resume(path).projects:
            if project.name != "Triage Studio":
                continue
            if project.repository is None:
                continue
            assert slug_matches_name(project.repository, project.name)


class TestTheRenderedLatexCarriesOnlyOwnedLinks:
    """
    The same invariant one stage later.

    The content check alone would miss a renderer that paired a URL with the
    wrong title, so the assertion is repeated against the LaTeX actually
    produced — the artifact a reader clicks.
    """

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_no_rendered_link_is_a_foreign_repository(self, path):
        resume = load_resume(path)
        latex = LatexRenderer().render(resume)
        owned = {project.repository for project in linked_projects(resume)}
        for project in linked_projects(resume):
            fragment = "\\href{" + project.repository + "}"
            assert fragment in latex
        assert _WRONG_TRIAGE_STUDIO_REPOSITORY not in latex
        # No project link survives in the document that no project owns.
        for url in project_link_targets(latex):
            assert url in owned

    @pytest.mark.parametrize("path", content_files(), ids=lambda p: p.name)
    def test_a_project_without_a_repository_renders_no_link(self, path):
        resume = load_resume(path)
        latex = LatexRenderer().render(resume)
        assert latex.count("\\underline{Link}") == len(linked_projects(resume))


class TestTheOwnershipRuleActuallyCatchesMismatches:
    """
    Proof the rule above is not vacuous.

    A check that accepts everything passes just as green as a correct one, so
    the exact historical pairing is fed back through it and must be rejected.
    """

    def test_the_historical_defect_is_rejected(self):
        assert not slug_matches_name(
            "https://github.com/Sundar0603/Daily-Studies", "Triage Studio"
        )

    def test_a_correct_pairing_is_accepted(self):
        assert slug_matches_name(
            "https://github.com/Sundar0603/triage-studio", "Triage Studio"
        )

    def test_a_correct_pairing_survives_a_trailing_slash(self):
        assert slug_matches_name(
            "https://github.com/Sundar0603/resume-tailor/", "Resume Tailor"
        )

    def test_case_and_separators_do_not_defeat_the_match(self):
        assert slug_matches_name(
            "https://github.com/Sundar0603/Resume_Tailor.git", "resume tailor"
        )

    def test_a_generic_token_alone_does_not_prove_ownership(self):
        assert not slug_matches_name(
            "https://github.com/Sundar0603/chat-app", "Budget App"
        )

    def test_a_url_without_a_path_matches_nothing(self):
        assert not slug_matches_name("https://github.com", "Triage Studio")

    def test_the_slug_is_the_last_path_segment(self):
        assert (
            repository_slug("https://github.com/Sundar0603/triage-studio")
            == "triage-studio"
        )

    def test_query_and_fragment_are_not_part_of_the_slug(self):
        assert (
            repository_slug("https://github.com/o/triage-studio?tab=readme#top")
            == "triage-studio"
        )

    def test_short_and_generic_tokens_are_discarded(self):
        assert significant_tokens("The App") == set()
