"""
SkillsParser — parses the '# Skills' section of a resume.

Each '## Category' heading becomes a SkillCategory.
Each '- item' bullet becomes a skill within that category.
"""

import re
from typing import List

from .models import SkillCategory
from .metadata_parser import ParserError


class SkillsParser:
    """Parses the Skills section into a list of SkillCategory objects."""

    def parse(self, section_body: str) -> List[SkillCategory]:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Skills' section
            (without the heading line itself).

        Returns
        -------
        List[SkillCategory]
            One SkillCategory per '## Category' sub-heading.

        Raises
        ------
        ParserError
            If no skill categories are found.
        """
        categories: List[SkillCategory] = []

        # Split on any H2 heading inside the Skills section
        h2_pattern = re.compile(r'^## (.+)$', re.MULTILINE)
        matches = list(h2_pattern.finditer(section_body))

        if not matches:
            raise ParserError("Skills section contains no categories.")

        for idx, match in enumerate(matches):
            category_name = match.group(1).strip()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section_body)
            block = section_body[start:end]

            skills = self._parse_bullets(block)
            categories.append(SkillCategory(category=category_name, skills=skills))

        return categories

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_bullets(self, block: str) -> List[str]:
        """Extract all '- item' bullet lines from a text block."""
        items: List[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith('- '):
                items.append(stripped[2:].strip())
        return items
