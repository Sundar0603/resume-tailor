"""
Ordering: the serializer never reorders anything the Resume already decided.

Order is load-bearing downstream — the Quality Gate trims from the bottom to
fit one page, so the Generator deliberately puts the weakest item last.
"""

from src.renderer import MarkdownSerializer

from .conftest import make_resume, section_order


class TestSectionOrder:
    def test_follows_the_canonical_order(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert section_order(markdown) == [
            "Contact",
            "Summary",
            "Skills",
            "Work Experience",
            "Projects",
            "Education",
        ]

    def test_order_is_fixed_regardless_of_content(self):
        resume = make_resume()
        resume.projects = []
        markdown = MarkdownSerializer().serialize(resume)
        assert section_order(markdown) == [
            "Contact",
            "Summary",
            "Skills",
            "Work Experience",
            "Projects",
            "Education",
        ]


class TestEntityOrder:
    def test_experiences_keep_their_order(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        first = markdown.index("Role: Software Developer")
        second = markdown.index("Role: Project Trainee")
        assert first < second

    def test_reversing_experiences_reverses_the_output(self):
        resume = make_resume()
        resume.experiences = list(reversed(resume.experiences))
        markdown = MarkdownSerializer().serialize(resume)
        assert markdown.index("Role: Project Trainee") < markdown.index(
            "Role: Software Developer"
        )

    def test_projects_keep_their_order(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.index("Name: Triage Studio") < markdown.index("Name: SOCrates")

    def test_reversing_projects_reverses_the_output(self):
        resume = make_resume()
        resume.projects = list(reversed(resume.projects))
        markdown = MarkdownSerializer().serialize(resume)
        assert markdown.index("Name: SOCrates") < markdown.index("Name: Triage Studio")

    def test_skill_categories_keep_their_order(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.index("## Security") < markdown.index("## Backend")

    def test_education_entries_keep_their_order(self):
        resume = make_resume()
        second = resume.education[0].model_copy(update={"institution": "Second School"})
        resume.education = resume.education + [second]
        markdown = MarkdownSerializer().serialize(resume)
        assert markdown.index("Institution: Anna University") < markdown.index(
            "Institution: Second School"
        )


class TestListOrder:
    def test_highlights_keep_their_order(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        assert markdown.index("- Built ingestion pipelines.") < markdown.index(
            "- Designed workflows."
        )

    def test_highlights_are_not_sorted(self):
        resume = make_resume()
        resume.experiences[0].highlights = ["Zebra work.", "Alpha work."]
        markdown = MarkdownSerializer().serialize(resume)
        assert markdown.index("- Zebra work.") < markdown.index("- Alpha work.")

    def test_skills_keep_their_order(self):
        resume = make_resume()
        resume.skills[0].skills = ["Zebra", "Alpha", "Mango"]
        markdown = MarkdownSerializer().serialize(resume)
        rendered = markdown.split("## Security\n\n")[1].split("\n\n")[0]
        assert rendered == "- Zebra\n- Alpha\n- Mango"

    def test_technologies_and_domains_keep_their_order(self):
        resume = make_resume()
        resume.experiences[0].technologies = ["Zebra", "Alpha"]
        resume.experiences[0].domains = ["Yankee", "Bravo"]
        markdown = MarkdownSerializer().serialize(resume)
        assert markdown.index("- Zebra") < markdown.index("- Alpha")
        assert markdown.index("- Yankee") < markdown.index("- Bravo")

    def test_duplicate_skills_are_not_deduplicated(self):
        resume = make_resume()
        resume.skills[0].skills = ["Redis", "Redis"]
        markdown = MarkdownSerializer().serialize(resume)
        rendered = markdown.split("## Security\n\n")[1].split("\n\n")[0]
        assert rendered == "- Redis\n- Redis"


class TestFieldOrder:
    def test_experience_fields_follow_the_schema(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        block = markdown.split("## Experience\n\n")[1]
        labels = [
            line.split(":")[0]
            for line in block.splitlines()
            if line and not line.startswith("-") and ":" in line
        ]
        assert labels[:8] == [
            "Company",
            "Role",
            "Employment Type",
            "Duration",
            "Location",
            "Technologies",
            "Domains",
            "Highlights",
        ]

    def test_education_fields_follow_the_schema(self):
        markdown = MarkdownSerializer().serialize(make_resume())
        block = markdown.split("## Degree\n\n")[1]
        labels = [line.split(":")[0] for line in block.splitlines() if ":" in line]
        assert labels[:6] == [
            "Institution",
            "Degree",
            "Major",
            "Duration",
            "CGPA",
            "Location",
        ]
