"""
EducationParser — parses the '# Education' section of a resume.

Each '## Degree' sub-block becomes an Education object.
"""

from typing import List

from .models import Education
from .metadata_parser import ParserError
from ..helpers._section_utils import split_sub_blocks, get_scalar


class EducationParser:
    """Parses the Education section into a list of Education objects."""

    def parse(self, section_body: str) -> List[Education]:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Education' section
            (without the heading line itself).

        Returns
        -------
        List[Education]
            One Education per '## Degree' sub-block.

        Raises
        ------
        ParserError
            If no degree blocks are found or required fields are missing.
        """
        blocks = split_sub_blocks(section_body, "Degree")

        if not blocks:
            raise ParserError("Education section contains no '## Degree' blocks.")

        education_list: List[Education] = []
        for idx, block in enumerate(blocks, start=1):
            education_list.append(self._parse_block(block, idx))

        return education_list

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_block(self, block: str, idx: int) -> Education:
        """Parse a single '## Degree' block into an Education object."""
        institution = get_scalar(block, "Institution")
        degree = get_scalar(block, "Degree")
        major = get_scalar(block, "Major")
        duration = get_scalar(block, "Duration")
        cgpa = get_scalar(block, "CGPA")
        location = get_scalar(block, "Location")

        for field_name, value in (
            ("Institution", institution),
            ("Degree", degree),
            ("Major", major),
            ("Duration", duration),
        ):
            if value is None:
                raise ParserError(
                    f"Degree block {idx} is missing required field: '{field_name}'"
                )

        return Education(
            institution=institution,
            degree=degree,
            major=major,
            duration=duration,
            cgpa=cgpa,
            location=location,
        )
