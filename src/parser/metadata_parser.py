"""
MetadataParser — parses YAML front matter from a resume Markdown document.

Expects the document to begin with a YAML block delimited by '---'.
Raises ParserError if the front matter is missing or required fields are absent.
"""

import yaml
from .models import Metadata


class ParserError(Exception):
    """Raised when the document violates the resume schema."""


class MetadataParser:
    """Parses YAML front matter into a Metadata object."""

    def parse(self, raw: str) -> Metadata:
        """
        Parameters
        ----------
        raw : str
            The full raw Markdown document text.

        Returns
        -------
        Metadata
            Populated Metadata dataclass.

        Raises
        ------
        ParserError
            If front matter is missing or required fields are absent.
        """
        front_matter = self._extract_front_matter(raw)
        data = self._parse_yaml(front_matter)

        for required_field in ("resume", "template", "version"):
            if required_field not in data:
                raise ParserError(
                    f"Metadata is missing required field: '{required_field}'"
                )

        return Metadata(
            resume=str(data["resume"]),
            template=str(data["template"]),
            version=str(data["version"]),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_front_matter(self, raw: str) -> str:
        """Return the YAML text between the opening and closing '---' delimiters."""
        lines = raw.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ParserError(
                "Document does not begin with YAML front matter ('---')."
            )

        end_index = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = i
                break

        if end_index is None:
            raise ParserError("YAML front matter is not closed with '---'.")

        return "\n".join(lines[1:end_index])

    def _parse_yaml(self, text: str) -> dict:
        """Parse a YAML string and return a dict."""
        try:
            result = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ParserError(f"Failed to parse YAML front matter: {exc}") from exc

        if not isinstance(result, dict):
            raise ParserError("YAML front matter did not produce a mapping.")

        return result
