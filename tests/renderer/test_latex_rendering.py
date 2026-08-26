"""
Resume content reaches the template, in source order, unaltered.

Ordering is the load-bearing property here: the Quality Gate trims from the
bottom, so the last thing rendered is the first thing lost.
"""

from src.parser.models import EntitySource
from src.renderer import LatexRenderer

from .conftest import make_generated_resume, make_resume


def render(resume=None):
    return LatexRenderer().render(resume if resume is not None else make_resume())


def section(latex, name):
    """Return the body of one \\section, up to the next one."""
    body = latex.split("\\section{\\color{airforceblue}" + name + "}")[1]
    return body.split("\\section{")[0]


def positions(latex, *needles):
    return [latex.index(needle) for needle in needles]


class TestContact:
    def test_every_contact_field_is_rendered(self):
        latex = render()
        contact = make_resume().contact
        assert contact.name in latex
        assert contact.phone in latex
        assert contact.email in latex
        assert contact.linkedin in latex
        assert contact.github in latex

    def test_the_email_is_both_a_mailto_and_visible_text(self):
        resume = make_resume()
        latex = render(resume)
        assert "mailto:" + resume.contact.email in latex
        assert "\\color{blue}" + resume.contact.email in latex

    def test_the_links_keep_the_templates_href_mechanism(self):
        resume = make_resume()
        latex = render(resume)
        assert "\\href{" + resume.contact.linkedin + "}" in latex
        assert "\\href{" + resume.contact.github + "}" in latex


class TestSummary:
    def test_the_summary_is_preserved_exactly(self):
        resume = make_resume()
        assert resume.summary in render(resume)

    def test_the_summary_is_not_split_into_bullets(self):
        resume = make_resume()
        body = section(render(resume), "SUMMARY")
        assert "\\resumeItem" not in body


class TestSkills:
    def test_every_category_and_skill_appears(self):
        resume = make_resume()
        body = section(render(resume), "TECHNICAL SKILLS")
        for category in resume.skills:
            assert category.category + ":" in body
            for skill in category.skills:
                assert skill in body

    def test_category_order_is_preserved(self):
        resume = make_resume()
        body = section(render(resume), "TECHNICAL SKILLS")
        names = [category.category for category in resume.skills]
        assert positions(body, *names) == sorted(positions(body, *names))

    def test_skill_order_within_a_category_is_preserved(self):
        resume = make_resume()
        resume.skills[0].skills = ["Zulu", "Alpha", "Mike"]
        body = section(render(resume), "TECHNICAL SKILLS")
        assert "Zulu, Alpha, Mike" in body

    def test_skills_are_not_deduplicated(self):
        resume = make_resume()
        resume.skills[0].skills = ["Java", "Java"]
        body = section(render(resume), "TECHNICAL SKILLS")
        assert "Java, Java" in body

    def test_a_category_becomes_one_row(self):
        resume = make_resume()
        body = section(render(resume), "TECHNICAL SKILLS")
        assert body.count("\\textbf{\\normalsize{") == len(resume.skills)


class TestExperience:
    def test_every_experience_is_rendered(self):
        resume = make_resume()
        body = section(render(resume), "WORK EXPERIENCE")
        assert body.count("\\resumeSubheading") == len(resume.experiences)

    def test_experience_order_is_preserved(self):
        resume = make_resume()
        body = section(render(resume), "WORK EXPERIENCE")
        roles = [item.role for item in resume.experiences]
        assert positions(body, *roles) == sorted(positions(body, *roles))

    def test_the_subheading_carries_company_location_role_and_duration(self):
        resume = make_resume()
        first = resume.experiences[0]
        body = section(render(resume), "WORK EXPERIENCE")
        assert "{" + first.company + "}{" + (first.location or "") + "}" in body
        assert "{" + first.role + "}{" + first.duration + "}" in body

    def test_highlight_order_is_preserved(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["First one", "Second one", "Third one"]
        body = section(render(resume), "WORK EXPERIENCE")
        assert positions(body, "First one", "Second one", "Third one") == sorted(
            positions(body, "First one", "Second one", "Third one")
        )

    def test_every_highlight_becomes_a_resume_item(self):
        resume = make_resume()
        body = section(render(resume), "WORK EXPERIENCE")
        expected = sum(len(item.highlights) for item in resume.experiences)
        assert body.count("\\resumeItem{") == expected

    def test_highlight_text_is_preserved_exactly(self):
        resume = make_resume()
        for experience in resume.experiences:
            for highlight in experience.highlights:
                assert highlight in render(resume)


class TestDroppedFields:
    """Fields the template's design has no place for. Documented, not accidental."""

    def test_employment_type_is_not_rendered(self):
        resume = make_resume()
        resume.experiences[0].employment_type = "Zzyzx Employment Type"
        assert "Zzyzx Employment Type" not in render(resume)

    def test_experience_technologies_and_domains_are_not_rendered(self):
        resume = make_resume()
        resume.experiences[0].technologies = ["Zzyzxtech"]
        resume.experiences[0].domains = ["Zzyzxdomain"]
        latex = render(resume)
        assert "Zzyzxtech" not in latex
        assert "Zzyzxdomain" not in latex

    def test_project_type_and_domains_are_not_rendered(self):
        resume = make_resume()
        resume.projects[0].type = "Zzyzxtype"
        resume.projects[0].domains = ["Zzyzxdomain"]
        latex = render(resume)
        assert "Zzyzxtype" not in latex
        assert "Zzyzxdomain" not in latex


class TestProjects:
    def test_every_project_is_rendered(self):
        resume = make_resume()
        body = section(render(resume), "PROJECTS")
        for project in resume.projects:
            assert project.name in body

    def test_project_order_is_preserved(self):
        resume = make_resume()
        body = section(render(resume), "PROJECTS")
        names = [project.name for project in resume.projects]
        assert positions(body, *names) == sorted(positions(body, *names))

    def test_technology_order_is_preserved_in_the_title(self):
        resume = make_resume()
        resume.projects[0].technologies = ["Zulu", "Alpha", "Mike"]
        body = section(render(resume), "PROJECTS")
        assert "\\textit{(Zulu, Alpha, Mike)}" in body

    def test_the_repository_becomes_a_link(self):
        resume = make_resume()
        body = section(render(resume), "PROJECTS")
        assert "\\href{" + resume.projects[0].repository + "}" in body
        assert "\\underline{Link}" in body

    def test_highlight_order_is_preserved(self):
        resume = make_resume()
        resume.projects[0].highlights = ["Alpha first", "Bravo second"]
        body = section(render(resume), "PROJECTS")
        assert body.index("Alpha first") < body.index("Bravo second")


class TestEducation:
    def test_every_entry_is_rendered(self):
        resume = make_resume()
        body = section(render(resume), "EDUCATION")
        for entry in resume.education:
            assert entry.institution in body
            assert entry.degree in body
            assert entry.major in body
            assert entry.duration in body

    def test_education_order_is_preserved(self):
        resume = make_resume()
        second = resume.education[0].model_copy(deep=True)
        second.id = "edu_002"
        second.institution = "Second Institution"
        resume.education = resume.education + [second]
        body = section(render(resume), "EDUCATION")
        assert body.index(resume.education[0].institution) < body.index(
            "Second Institution"
        )

    def test_the_cgpa_joins_the_institution(self):
        resume = make_resume()
        body = section(render(resume), "EDUCATION")
        assert "CGPA: " + resume.education[0].cgpa in body


class TestGeneratedEntities:
    def test_generated_entities_render_like_canonical_ones(self):
        resume = make_generated_resume()
        latex = LatexRenderer().render(resume)
        for project in resume.projects:
            assert project.name in latex

    def test_runtime_metadata_never_reaches_the_document(self):
        resume = make_generated_resume()
        latex = LatexRenderer().render(resume)
        assert EntitySource.GENERATED.value not in latex
        assert EntitySource.CANONICAL.value not in latex
        for entity in resume.projects + resume.skills + resume.education:
            assert entity.id not in latex
        for experience in resume.experiences:
            assert experience.id not in latex
