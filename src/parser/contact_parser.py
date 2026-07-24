"""
ContactParser — parses the '# Contact' section of a resume.
"""

from .models import Contact
from .metadata_parser import ParserError
from ..helpers._section_utils import get_scalar


class ContactParser:
    """Parses the Contact section into a Contact object."""

    def parse(self, section_body: str) -> Contact:
        """
        Parameters
        ----------
        section_body : str
            The text content of the '# Contact' section
            (without the heading line itself).

        Returns
        -------
        Contact
            Populated Contact dataclass.

        Raises
        ------
        ParserError
            If any required field is missing.
        """
        name = get_scalar(section_body, "Name")
        phone = get_scalar(section_body, "Phone")
        email = get_scalar(section_body, "Email")
        linkedin = get_scalar(section_body, "LinkedIn")
        github = get_scalar(section_body, "GitHub")

        for field_name, value in (
            ("Name", name),
            ("Phone", phone),
            ("Email", email),
            ("LinkedIn", linkedin),
            ("GitHub", github),
        ):
            if value is None:
                raise ParserError(
                    f"Contact section is missing required field: '{field_name}'"
                )

        return Contact(
            name=name,
            phone=phone,
            email=email,
            linkedin=linkedin,
            github=github,
        )
