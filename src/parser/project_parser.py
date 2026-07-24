"""
ProjectParser — parses the '# Projects' section of a resume.

Each '## Project' sub-block becomes a Project object.
"""

from typing import List

from .models import Project
from .metadata_parser import ParserError
from ..helpers._section_utils import split_sub_blocks, get_scalar, get_list


class ProjectParser:
    """Parses the Projects section into a list of Project objects."""

    def parse(self, section_body: str) -> List[Project]:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Projects' section
            (without the heading line itself).

        Returns
        -------
        List[Project]
            One Project per '## Project' sub-block.
            Returns an empty list if the section has no project blocks.

        Raises
        ------
        ParserError
            If a project block is missing required fields.
        """
        blocks = split_sub_blocks(section_body, "Project")

        projects: List[Project] = []
        for idx, block in enumerate(blocks, start=1):
            projects.append(self._parse_block(block, idx))

        return projects

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_block(self, block: str, idx: int) -> Project:
        """Parse a single '## Project' block into a Project object."""
        name = get_scalar(block, "Name")
        project_type = get_scalar(block, "Type")
        repository = get_scalar(block, "Repository")
        technologies = get_list(block, "Technologies")
        domains = get_list(block, "Domains")
        highlights = get_list(block, "Highlights")

        for field_name, value in (
            ("Name", name),
            ("Type", project_type),
        ):
            if value is None:
                raise ParserError(
                    f"Project block {idx} is missing required field: '{field_name}'"
                )

        if not highlights:
            raise ParserError(
                f"Project block {idx} ('{name}') has no Highlights."
            )

        return Project(
            name=name,
            type=project_type,
            repository=repository,
            technologies=technologies,
            domains=domains,
            highlights=highlights,
        )
