"""
ResumeParser — top-level orchestrator.

Reads a Markdown resume file, delegates each section to the appropriate
sub-parser, and returns a fully populated Resume object.
"""

import re
from pathlib import Path

from .models import Resume
from .metadata_parser import MetadataParser, ParserError
from .contact_parser import ContactParser
from .summary_parser import SummaryParser
from .skills_parser import SkillsParser
from .experience_parser import ExperienceParser
from .project_parser import ProjectParser
from .education_parser import EducationParser
from ..helpers._section_utils import split_top_level_sections


class ResumeParser:
    """
    Parses a schema-compliant Markdown resume file into a Resume object.

    Usage
    -----
    parser = ResumeParser()
    resume = parser.parse("content/cybersecurity_resume.md")
    """

    def __init__(self) -> None:
        self._metadata_parser = MetadataParser()
        self._contact_parser = ContactParser()
        self._summary_parser = SummaryParser()
        self._skills_parser = SkillsParser()
        self._experience_parser = ExperienceParser()
        self._project_parser = ProjectParser()
        self._education_parser = EducationParser()

    def parse(self, file_path: str) -> Resume:
        """
        Parse a Markdown resume file.

        Parameters
        ----------
        file_path : str
            Path to the Markdown resume file.

        Returns
        -------
        Resume
            Fully populated Resume object.

        Raises
        ------
        ParserError
            If the file cannot be read or the document violates the schema.
        FileNotFoundError
            If the file does not exist.
        """
        raw = self._read_file(file_path)
        body = self._strip_front_matter(raw)
        sections = split_top_level_sections(body)

        metadata = self._metadata_parser.parse(raw)

        contact_body = self._require_section(sections, "contact", "Contact")
        contact = self._contact_parser.parse(contact_body)

        summary_body = self._require_section(sections, "summary", "Summary")
        summary = self._summary_parser.parse(summary_body)

        skills_body = self._require_section(sections, "skills", "Skills")
        skills = self._skills_parser.parse(skills_body)

        experience_body = self._require_section(
            sections, "work experience", "Work Experience"
        )
        experiences = self._experience_parser.parse(experience_body)

        # Projects section is optional — return empty list if absent
        projects_body = sections.get("projects", "")
        projects = self._project_parser.parse(projects_body) if projects_body else []

        education_body = self._require_section(sections, "education", "Education")
        education = self._education_parser.parse(education_body)

        return Resume(
            metadata=metadata,
            contact=contact,
            summary=summary,
            skills=skills,
            experiences=experiences,
            projects=projects,
            education=education,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_file(self, file_path: str) -> str:
        """Read and return the full text of a file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {file_path}")
        return path.read_text(encoding="utf-8")

    def _strip_front_matter(self, raw: str) -> str:
        """
        Remove the YAML front matter block from the raw document and
        return the remaining Markdown body.
        """
        lines = raw.splitlines()
        if not lines or lines[0].strip() != "---":
            return raw  # No front matter — return as-is

        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1:])

        return raw  # Closing delimiter not found — return as-is

    def _require_section(self, sections: dict, key: str, display_name: str) -> str:
        """
        Return the body of a required section, raising ParserError if absent.
        """
        body = sections.get(key)
        if body is None:
            raise ParserError(f"Required section '# {display_name}' not found in resume.")
        return body
