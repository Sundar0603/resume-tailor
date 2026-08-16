"""
MarkdownSerializer — renders a Resume object as canonical Markdown.

The inverse of :class:`~src.parser.resume_parser.ResumeParser`. Deterministic,
LLM-free, and read-only: the Resume is never modified, no field is reordered,
and no content is rewritten, shortened or cleaned up. It is a serializer, not
an editor.

Only fields defined by ``docs/RESUME_SCHEMA.md`` are emitted. Runtime-only
state carried on the models — ``id`` and ``source`` — is deliberately dropped,
because it is regenerated on every parse and has no place in the canonical
document.
"""

import json
from typing import List, Optional

import yaml

from ..parser.models import (
    Contact,
    Education,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)
from .exceptions import SerializationError

# A line consisting only of this is a separator to the parser, never content.
SEPARATOR = "---"


class MarkdownSerializer:
    """Renders a Resume into the canonical Markdown representation."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def serialize(self, resume: Resume) -> str:
        """
        Render a Resume as a complete canonical Markdown document.

        Parameters
        ----------
        resume : Resume
            The resume to render. It is read only, never modified.

        Returns
        -------
        str
            The full document, including YAML front matter, ending in a
            single newline.

        Raises
        ------
        SerializationError
            If the Resume holds a value that canonical Markdown cannot
            represent.
        """
        sections = [
            self._contact(resume.contact),
            self._summary(resume.summary),
            self._skills(resume.skills),
            self._experiences(resume.experiences),
            self._projects(resume.projects),
            self._education(resume.education),
        ]

        lines = self._front_matter(resume.metadata) + [""]
        lines.extend(self._join_separated(sections))
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _front_matter(self, metadata: Metadata) -> List[str]:
        """Render the YAML front matter block."""
        return [
            SEPARATOR,
            "resume: " + self._yaml_value(metadata.resume, "resume"),
            "template: " + self._yaml_value(metadata.template, "template"),
            "version: " + self._yaml_value(metadata.version, "version"),
            SEPARATOR,
        ]

    def _contact(self, contact: Contact) -> List[str]:
        """Render the Contact section. All five fields are required."""
        fields = (
            ("Name", contact.name, "name"),
            ("Phone", contact.phone, "phone"),
            ("Email", contact.email, "email"),
            ("LinkedIn", contact.linkedin, "linkedin"),
            ("GitHub", contact.github, "github"),
        )
        groups = [
            self._scalar(label, value, "contact", field, required=True)
            for label, value, field in fields
        ]
        return ["# Contact", ""] + self._join_blank(groups)

    def _summary(self, summary: str) -> List[str]:
        """Render the Summary section as a paragraph, never as bullets."""
        if not summary.strip():
            raise SerializationError(
                "summary: the value is empty, but the parser requires a "
                "non-empty Summary section."
            )
        for line in summary.splitlines():
            if line.strip() == SEPARATOR:
                raise SerializationError(
                    "summary: contains a line consisting only of '---', which "
                    "the parser treats as a separator and discards."
                )
        return ["# Summary", ""] + summary.splitlines()

    def _skills(self, categories: List[SkillCategory]) -> List[str]:
        """Render the Skills section. Categories are separated by a blank line."""
        blocks = [self._skill_block(category) for category in categories]
        if not blocks:
            return ["# Skills"]
        return ["# Skills", ""] + self._join_blank(blocks)

    def _experiences(self, experiences: List[Experience]) -> List[str]:
        """Render the Work Experience section."""
        blocks = [self._experience_block(item) for item in experiences]
        return self._section("Work Experience", blocks)

    def _projects(self, projects: List[Project]) -> List[str]:
        """Render the Projects section, which may legitimately be empty."""
        blocks = [self._project_block(item) for item in projects]
        return self._section("Projects", blocks)

    def _education(self, education: List[Education]) -> List[str]:
        """Render the Education section."""
        blocks = [self._education_block(item) for item in education]
        return self._section("Education", blocks)

    # ------------------------------------------------------------------
    # Entity blocks
    # ------------------------------------------------------------------

    def _skill_block(self, category: SkillCategory) -> List[str]:
        """Render one skill category as an H2 heading plus a tight bullet list."""
        entity_id = category.id or "skill category"
        if not category.category.strip():
            raise SerializationError(
                "{}: the category name is empty, so it cannot be written as a "
                "heading.".format(entity_id)
            )
        self._check_value(category.category, entity_id, "category")

        lines = ["## " + category.category]
        if not category.skills:
            return lines

        lines.append("")
        for index, skill in enumerate(category.skills):
            self._check_item(skill, entity_id, "skills", index)
            lines.append("- " + skill)
        return lines

    def _experience_block(self, experience: Experience) -> List[str]:
        """Render one work experience. Field order follows RESUME_SCHEMA.md."""
        entity_id = experience.id or "experience"
        groups = [
            self._scalar("Company", experience.company, entity_id, "company", True),
            self._scalar("Role", experience.role, entity_id, "role", True),
            self._scalar(
                "Employment Type",
                experience.employment_type,
                entity_id,
                "employment_type",
                True,
            ),
            self._scalar("Duration", experience.duration, entity_id, "duration", True),
            self._scalar("Location", experience.location, entity_id, "location"),
            self._list_block(
                "Technologies", experience.technologies, entity_id, "technologies"
            ),
            self._list_block("Domains", experience.domains, entity_id, "domains"),
            self._list_block(
                "Highlights",
                experience.highlights,
                entity_id,
                "highlights",
                spaced=True,
            ),
        ]
        return ["## Experience", ""] + self._join_blank(groups)

    def _project_block(self, project: Project) -> List[str]:
        """Render one project. Absent optional fields are omitted entirely."""
        entity_id = project.id or "project"
        groups = [
            self._scalar("Name", project.name, entity_id, "name", True),
            self._scalar("Type", project.type, entity_id, "type", True),
            self._scalar("Repository", project.repository, entity_id, "repository"),
            self._list_block(
                "Technologies", project.technologies, entity_id, "technologies"
            ),
            self._list_block("Domains", project.domains, entity_id, "domains"),
            self._list_block(
                "Highlights", project.highlights, entity_id, "highlights", spaced=True
            ),
        ]
        return ["## Project", ""] + self._join_blank(groups)

    def _education_block(self, education: Education) -> List[str]:
        """Render one education entry."""
        entity_id = education.id or "education"
        groups = [
            self._scalar(
                "Institution", education.institution, entity_id, "institution", True
            ),
            self._scalar("Degree", education.degree, entity_id, "degree", True),
            self._scalar("Major", education.major, entity_id, "major", True),
            self._scalar("Duration", education.duration, entity_id, "duration", True),
            self._scalar("CGPA", education.cgpa, entity_id, "cgpa"),
            self._scalar("Location", education.location, entity_id, "location"),
        ]
        return ["## Degree", ""] + self._join_blank(groups)

    # ------------------------------------------------------------------
    # Field helpers
    # ------------------------------------------------------------------

    def _scalar(
        self,
        label: str,
        value: Optional[str],
        entity_id: str,
        field: str,
        required: bool = False,
    ) -> List[str]:
        """
        Render one 'Label: value' line.

        An absent optional value produces no line at all. Emitting a bare
        'Label:' instead would be worse than cosmetic: the parser's scalar
        pattern spans the newline and would swallow the following field's
        entire line.
        """
        if value is None or not value.strip():
            if required:
                raise SerializationError(
                    "{}.{}: '{}' is required but the value is empty.".format(
                        entity_id, field, label
                    )
                )
            return []
        self._check_value(value, entity_id, field)
        return ["{}: {}".format(label, value)]

    def _list_block(
        self,
        label: str,
        items: List[str],
        entity_id: str,
        field: str,
        spaced: bool = False,
    ) -> List[str]:
        """
        Render a 'Label:' line followed by a bullet list.

        An empty list produces no block. ``spaced`` puts a blank line between
        bullets, matching how highlights are written in ``content/*.md``.
        """
        if not items:
            return []

        lines = ["{}:".format(label), ""]
        for index, item in enumerate(items):
            if spaced and index:
                lines.append("")
            self._check_item(item, entity_id, field, index)
            lines.append("- " + item)
        return lines

    def _yaml_value(self, text: str, field: str) -> str:
        """
        Render a front-matter value, quoting it only when it needs quoting.

        The parser runs front matter through ``yaml.safe_load`` and then
        ``str()``, which retypes bare scalars: ``1.10`` becomes ``1.1`` and
        ``no`` becomes ``False``. Values that survive that cycle unchanged are
        emitted bare so ordinary output matches the schema's own examples;
        anything else is quoted.
        """
        self._check_value(text, "metadata", field)
        if text:
            try:
                loaded = yaml.safe_load("key: " + text)
            except yaml.YAMLError:
                loaded = None
            if (
                isinstance(loaded, dict)
                and list(loaded) == ["key"]
                and loaded["key"] is not None
                and str(loaded["key"]) == text
            ):
                return text
        return json.dumps(text)

    # ------------------------------------------------------------------
    # Round-trip guards
    # ------------------------------------------------------------------

    def _check_value(self, value: str, entity_id: str, field: str) -> None:
        """Raise if a value cannot survive being written and re-parsed."""
        if "\n" in value or "\r" in value:
            raise SerializationError(
                "{}.{}: the value contains a line break, which canonical "
                "Markdown cannot represent on a single field line.".format(
                    entity_id, field
                )
            )
        if value.strip() == SEPARATOR:
            raise SerializationError(
                "{}.{}: the value is '---', which the parser treats as a "
                "separator and discards.".format(entity_id, field)
            )

    def _check_item(
        self, item: str, entity_id: str, field: str, index: int
    ) -> None:
        """Raise if a bullet cannot survive being written and re-parsed."""
        if not item.strip():
            raise SerializationError(
                "{}.{}[{}]: the item is empty. An empty bullet truncates the "
                "rest of its list when the document is re-parsed.".format(
                    entity_id, field, index
                )
            )
        self._check_value(item, entity_id, "{}[{}]".format(field, index))

    # ------------------------------------------------------------------
    # Assembly helpers
    # ------------------------------------------------------------------

    def _section(self, title: str, blocks: List[List[str]]) -> List[str]:
        """Render an H1 section whose entity blocks are separated by '---'."""
        if not blocks:
            return ["# " + title]
        return ["# " + title, ""] + self._join_separated(blocks)

    def _join_blank(self, groups: List[List[str]]) -> List[str]:
        """Concatenate non-empty line groups, separated by a single blank line."""
        lines = []  # type: List[str]
        for group in groups:
            if not group:
                continue
            if lines:
                lines.append("")
            lines.extend(group)
        return lines

    def _join_separated(self, blocks: List[List[str]]) -> List[str]:
        """
        Concatenate non-empty blocks, separated by a '---' horizontal rule.

        The rule only ever lands after the last bullet of a block, which is
        where the parser tolerates it. Inside a bullet run it would truncate
        the list.
        """
        lines = []  # type: List[str]
        for block in blocks:
            if not block:
                continue
            if lines:
                lines.extend(["", SEPARATOR, ""])
            lines.extend(block)
        return lines
