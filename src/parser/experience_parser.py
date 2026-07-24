"""
ExperienceParser — parses the '# Work Experience' section of a resume.

Each '## Experience' sub-block becomes an Experience object.
"""

from typing import List

from .models import Experience
from .metadata_parser import ParserError
from ..helpers._section_utils import split_sub_blocks, get_scalar, get_list


class ExperienceParser:
    """Parses the Work Experience section into a list of Experience objects."""

    def parse(self, section_body: str) -> List[Experience]:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Work Experience' section
            (without the heading line itself).

        Returns
        -------
        List[Experience]
            One Experience per '## Experience' sub-block.

        Raises
        ------
        ParserError
            If no experience blocks are found or required fields are missing.
        """
        blocks = split_sub_blocks(section_body, "Experience")

        if not blocks:
            raise ParserError("Work Experience section contains no '## Experience' blocks.")

        experiences: List[Experience] = []
        for idx, block in enumerate(blocks, start=1):
            experiences.append(self._parse_block(block, idx))

        return experiences

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_block(self, block: str, idx: int) -> Experience:
        """Parse a single '## Experience' block into an Experience object."""
        company = get_scalar(block, "Company")
        role = get_scalar(block, "Role")
        employment_type = get_scalar(block, "Employment Type")
        duration = get_scalar(block, "Duration")
        location = get_scalar(block, "Location")
        technologies = get_list(block, "Technologies")
        domains = get_list(block, "Domains")
        highlights = get_list(block, "Highlights")

        for field_name, value in (
            ("Company", company),
            ("Role", role),
            ("Employment Type", employment_type),
            ("Duration", duration),
        ):
            if value is None:
                raise ParserError(
                    f"Experience block {idx} is missing required field: '{field_name}'"
                )

        if not highlights:
            raise ParserError(
                f"Experience block {idx} ('{company}') has no Highlights."
            )

        return Experience(
            company=company,
            role=role,
            employment_type=employment_type,
            duration=duration,
            location=location,
            technologies=technologies,
            domains=domains,
            highlights=highlights,
        )
