"""
SummaryParser — parses the '# Summary' section of a resume.
"""

from .metadata_parser import ParserError


class SummaryParser:
    """Parses the Summary section into a plain string."""

    def parse(self, section_body: str) -> str:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Summary' section
            (without the heading line itself).

        Returns
        -------
        str
            The summary text, stripped of leading/trailing whitespace.

        Raises
        ------
        ParserError
            If the summary body is empty.
        """
        # Remove Markdown horizontal rules (---) used as visual separators
        # between sections — they are not part of the summary content.
        lines = [
            line for line in section_body.splitlines()
            if line.strip() != "---"
        ]
        summary = "\n".join(lines).strip()
        if not summary:
            raise ParserError("Summary section is empty.")
        return summary
