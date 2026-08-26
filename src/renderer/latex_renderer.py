"""
LatexRenderer — renders a Resume object into a complete LaTeX document.

Populates the frozen templates in ``templates/`` with resume content. The
template is the sole authority on visual design: this module never changes a
font size, a margin, a spacing value or a package, and never shrinks content to
fit a page. Fitting is the Quality Gate's job.

Deterministic, LLM-free and read-only. The Resume is never modified, nothing is
reordered, and no content is rewritten. Runtime-only state carried on the models
— ``id`` and ``source`` — is deliberately dropped, exactly as in
:class:`~src.renderer.markdown_serializer.MarkdownSerializer`.

Five model fields have no place in the template's design and are dropped:
``Experience.employment_type``, ``Experience.technologies``,
``Experience.domains``, ``Project.type`` and ``Project.domains``. They remain
runtime-only, feeding the Planner and Generator without reaching the PDF.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from ..parser.models import (
    Contact,
    Education,
    Experience,
    Project,
    Resume,
    SkillCategory,
)
from .exceptions import RenderingError

DEFAULT_TEMPLATE_DIRECTORY = "templates"
DEFAULT_OUTPUT_DIRECTORY = "output/resumes/latex"
TEMPLATE_SUFFIX = ".tex"

# Every placeholder a template must declare. A template missing one of these is
# an error: silently rendering a resume with no summary would be worse.
REQUIRED_PLACEHOLDERS = (
    "CONTACT_NAME",
    "CONTACT_PHONE",
    "CONTACT_EMAIL",
    "CONTACT_EMAIL_URL",
    "CONTACT_LINKEDIN",
    "CONTACT_GITHUB",
    "SUMMARY",
    "SKILLS",
    "EXPERIENCE",
    "PROJECTS",
    "EDUCATION",
)

_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Characters LaTeX reads as markup. Applied in a single pass so that the
# replacement for '\' cannot itself be re-escaped by a later rule.
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(char) for char in _ESCAPES))

# Inside \href's first argument hyperref reads the URL almost verbatim. Only
# these five would break it, and '_', '&', '~', '?' and '=' must be left alone
# or the link stops resolving.
_URL_ESCAPES = {
    "\\": r"\textbackslash{}",
    "%": r"\%",
    "#": r"\#",
    "{": r"\{",
    "}": r"\}",
}
_URL_ESCAPE_RE = re.compile("|".join(re.escape(char) for char in _URL_ESCAPES))

# Punctuation a model routinely emits that pdflatex cannot set directly.
# Anything non-ASCII outside this table raises rather than being dropped.
_TRANSLITERATIONS = {
    "–": "--",
    "—": "---",
    "‘": "`",
    "’": "'",
    "“": "``",
    "”": "''",
    "…": r"\ldots{}",
    " ": " ",
    "•": r"$\bullet$",
    "×": r"$\times$",
    "→": r"$\rightarrow$",
    "°": r"$^{\circ}$",
    "−": "-",
}

_INDENT = " " * 6
_ITEM_INDENT = " " * 12

# Spacing the templates apply around project *titles* and at the head of an
# experience list. These are structural: every title gets one, in every master.
#
# There is deliberately NO per-bullet equivalent. The masters put negative
# vspace after individual *bullets* only sporadically — hand-tuned, document by
# document, to squeeze one particular resume onto one page. Reproducing that
# mechanically emits roughly -9pt after every bullet, which exceeds the
# inter-item gap and makes consecutive multi-line bullets overlap: the text
# collides and pdflatex reports nothing, because negative vspace produces no
# overfull warning. Page count even *improves*, since the content is collapsing
# on top of itself rather than fitting.
#
# Choosing compression per bullet to reach one page is exactly the layout
# optimization the Quality Gate owns. The renderer emits the structural spacing
# and stops.
_PROJECT_TITLE_SPACING = "\\vspace{-4px}"
_EXPERIENCE_LIST_LEAD = "\\vspace{-1pt}"


class LatexRenderer:
    """Renders a Resume into a complete, compilable LaTeX document."""

    def __init__(self, template_directory: str = DEFAULT_TEMPLATE_DIRECTORY) -> None:
        """
        Parameters
        ----------
        template_directory : str
            Directory holding ``{template}.tex``. The templates are read only
            and are never written to.
        """
        self._template_directory = Path(template_directory)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, resume: Resume) -> str:
        """
        Render a Resume as a complete LaTeX document.

        Parameters
        ----------
        resume : Resume
            The resume to render. It is read only, never modified.

        Returns
        -------
        str
            The full document, ready for pdflatex. Never a fragment.

        Raises
        ------
        RenderingError
            If the template is missing or unreadable, if it lacks a required
            placeholder, or if the resume holds content the template cannot
            represent.
        """
        template = self._load_template(resume.metadata.template)
        values = self._contact_values(resume.contact)
        values["SUMMARY"] = self._summary(resume.summary)
        values["SKILLS"] = "\n".join(self._skills(resume.skills))
        values["EXPERIENCE"] = "\n".join(self._experiences(resume.experiences))
        values["PROJECTS"] = "\n".join(self._projects(resume.projects))
        values["EDUCATION"] = "\n".join(self._education(resume.education))
        return self._substitute(template, values, resume.metadata.template)

    def render_to_file(
        self, resume: Resume, output_directory: str = DEFAULT_OUTPUT_DIRECTORY
    ) -> Path:
        """
        Render a Resume and write it to ``{output_directory}/{resume}.tex``.

        Parameters
        ----------
        resume : Resume
            The resume to render.
        output_directory : str
            Directory to write into. Created if it does not exist.

        Returns
        -------
        Path
            The path written.
        """
        latex = self.render(resume)
        directory = Path(output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (resume.metadata.resume + TEMPLATE_SUFFIX)
        destination.write_text(latex, encoding="utf-8")
        return destination

    # ------------------------------------------------------------------
    # Template loading and substitution
    # ------------------------------------------------------------------

    def _load_template(self, name: str) -> str:
        """Read ``{template_directory}/{name}.tex``."""
        if not name or not name.strip():
            raise RenderingError(
                "metadata.template: no template name is set, so no template "
                "can be selected."
            )
        path = self._template_directory / (name + TEMPLATE_SUFFIX)
        if not path.is_file():
            raise RenderingError(
                "metadata.template: no template named '{}' exists at {}.".format(
                    name, path
                )
            )
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise RenderingError(
                "metadata.template: template '{}' could not be read: {}".format(
                    name, error
                )
            )

    def _substitute(self, template: str, values: Dict[str, str], name: str) -> str:
        """
        Replace every placeholder, refusing to emit a partially filled document.

        Both directions are checked: a template missing a placeholder loses that
        section silently, and a placeholder left behind reaches pdflatex as
        literal braces.
        """
        for key in REQUIRED_PLACEHOLDERS:
            if "{{" + key + "}}" not in template:
                raise RenderingError(
                    "metadata.template: template '{}' does not declare the "
                    "required placeholder {{{{{}}}}}.".format(name, key)
                )
        rendered = template
        for key in REQUIRED_PLACEHOLDERS:
            rendered = rendered.replace("{{" + key + "}}", values[key])

        leftover = _PLACEHOLDER_RE.search(rendered)
        if leftover:
            raise RenderingError(
                "metadata.template: template '{}' contains the unknown "
                "placeholder {}, which the renderer cannot fill.".format(
                    name, leftover.group(0)
                )
            )
        return rendered

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _contact_values(self, contact: Contact) -> Dict[str, str]:
        """Render the five contact fields. The email appears as text and as a URL."""
        return {
            "CONTACT_NAME": self._text(contact.name, "contact", "name"),
            "CONTACT_PHONE": self._text(contact.phone, "contact", "phone"),
            "CONTACT_EMAIL": self._text(contact.email, "contact", "email"),
            "CONTACT_EMAIL_URL": self._url(contact.email, "contact", "email"),
            "CONTACT_LINKEDIN": self._url(contact.linkedin, "contact", "linkedin"),
            "CONTACT_GITHUB": self._url(contact.github, "contact", "github"),
        }

    def _summary(self, summary: str) -> str:
        """Render the summary as a paragraph, verbatim. No reflow, no rewrite."""
        if not summary.strip():
            raise RenderingError(
                "summary: the value is empty, but the template's SUMMARY "
                "section would render as a blank paragraph."
            )
        return self._text(summary, "summary", "summary")

    def _skills(self, categories: List[SkillCategory]) -> List[str]:
        """Render one bold-label row per category, in source order."""
        lines = []  # type: List[str]
        for category in categories:
            entity_id = category.id or "skill category"
            if not category.category.strip():
                raise RenderingError(
                    "{}.category: the category name is empty, so it cannot be "
                    "rendered as a label.".format(entity_id)
                )
            label = self._text(category.category, entity_id, "category")
            skills = ", ".join(
                self._text(skill, entity_id, "skills[{}]".format(index))
                for index, skill in enumerate(category.skills)
            )
            lines.append(
                "{}\\textbf{{\\normalsize{{{}:}}}}{{ \\normalsize{{{}}}}} \\\\".format(
                    _INDENT, label, skills
                )
            )
        return lines

    def _experiences(self, experiences: List[Experience]) -> List[str]:
        """Render the work-experience entries, in source order."""
        self._require_entries(experiences, "experiences", "WORK EXPERIENCE")
        lines = []  # type: List[str]
        for experience in experiences:
            lines.extend(self._experience_block(experience))
        return lines

    def _projects(self, projects: List[Project]) -> List[str]:
        """Render the project entries, in source order."""
        self._require_entries(projects, "projects", "PROJECTS")
        lines = []  # type: List[str]
        for project in projects:
            lines.extend(self._project_block(project))
        return lines

    def _education(self, education: List[Education]) -> List[str]:
        """Render the education entries, in source order."""
        self._require_entries(education, "education", "EDUCATION")
        lines = []  # type: List[str]
        for entry in education:
            lines.extend(self._education_block(entry))
        return lines

    # ------------------------------------------------------------------
    # Entity blocks
    # ------------------------------------------------------------------

    def _experience_block(self, experience: Experience) -> List[str]:
        """
        Render one experience as a subheading plus its bullet list.

        ``employment_type``, ``technologies`` and ``domains`` have no place in
        the template's design and are deliberately not rendered.
        """
        entity_id = experience.id or "experience"
        lines = [
            "",
            _INDENT + "\\resumeSubheading",
            "{}{{{}}}{{{}}}".format(
                _INDENT * 2,
                self._required(experience.company, entity_id, "company"),
                self._optional(experience.location, entity_id, "location"),
            ),
            "{}{{{}}}{{{}}}".format(
                _INDENT * 2,
                self._required(experience.role, entity_id, "role"),
                self._required(experience.duration, entity_id, "duration"),
            ),
        ]
        lines.extend(
            self._bullet_list(
                experience.highlights,
                entity_id,
                _INDENT * 2,
                lead=_EXPERIENCE_LIST_LEAD,
            )
        )
        return lines

    def _project_block(self, project: Project) -> List[str]:
        """
        Render one project as a title item plus its bullet list.

        ``type`` and ``domains`` are not part of the template's design.
        Technologies keep the title parenthetical the template already uses.
        """
        entity_id = project.id or "project"
        name = self._required(project.name, entity_id, "name")
        if project.technologies:
            technologies = ", ".join(
                self._text(item, entity_id, "technologies[{}]".format(index))
                for index, item in enumerate(project.technologies)
            )
            title = "\\resumeItem{{\\normalsize{{\\textbf{{{}}} -}} \\textit{{({})}}".format(
                name, technologies
            )
        else:
            title = "\\resumeItem{{\\normalsize{{\\textbf{{{}}}}}".format(name)
        if project.repository:
            title += " \\href{{{}}}{{\\color{{blue}}\\underline{{Link}}}}".format(
                self._url(project.repository, entity_id, "repository")
            )
        lines = ["", _INDENT + title + "}", _INDENT + _PROJECT_TITLE_SPACING]
        lines.extend(self._bullet_list(project.highlights, entity_id, _INDENT))
        return lines

    def _education_block(self, education: Education) -> List[str]:
        """Render one education entry. An absent CGPA removes its fragment entirely."""
        entity_id = education.id or "education"
        institution = self._required(education.institution, entity_id, "institution")
        if education.cgpa:
            institution += " \\textnormal{{\\small - CGPA: {}}}".format(
                self._required(education.cgpa, entity_id, "cgpa")
            )
        return [
            _INDENT + "\\resumeSubheading",
            "{}{{{}}}{{{}}}".format(
                _INDENT * 2,
                institution,
                self._optional(education.location, entity_id, "location"),
            ),
            "{}{{{} in {}}}{{{}}}".format(
                _INDENT * 2,
                self._required(education.degree, entity_id, "degree"),
                self._required(education.major, entity_id, "major"),
                self._required(education.duration, entity_id, "duration"),
            ),
            _INDENT + "\\vspace{-4pt}",
        ]

    def _bullet_list(
        self,
        highlights: List[str],
        entity_id: str,
        indent: str,
        lead: str = "",
    ) -> List[str]:
        """
        Render highlights as a resumeItem list, in order.

        An entry with no highlights emits no list at all: ``\\begin{itemize}``
        with no ``\\item`` is a LaTeX error, not an empty list.

        ``lead`` carries the template's own spacing at the head of the list.
        There is deliberately no per-bullet equivalent: see the note on
        ``_PROJECT_TITLE_SPACING``. A bullet must never carry trailing negative
        vspace, or consecutive multi-line bullets overlap.
        """
        if not highlights:
            return []
        lines = [indent + "\\resumeItemListStart"]
        if lead:
            lines.append(_ITEM_INDENT + lead)
        for index, highlight in enumerate(highlights):
            field = "highlights[{}]".format(index)
            if not highlight.strip():
                raise RenderingError(
                    "{}.{}: the highlight is empty, which renders as a bare "
                    "bullet.".format(entity_id, field)
                )
            lines.append(
                "{}\\resumeItem{{\\normalsize{{{}}}}}".format(
                    _ITEM_INDENT, self._text(highlight, entity_id, field)
                )
            )
        lines.append(indent + "\\resumeItemListEnd")
        return lines

    # ------------------------------------------------------------------
    # Field helpers
    # ------------------------------------------------------------------

    def _required(self, value: str, entity_id: str, field: str) -> str:
        """Escape a required field, raising when it is empty."""
        if not value or not value.strip():
            raise RenderingError(
                "{}.{}: the field is required but the value is empty.".format(
                    entity_id, field
                )
            )
        return self._text(value, entity_id, field)

    def _optional(self, value: Optional[str], entity_id: str, field: str) -> str:
        """
        Escape an optional field, rendering absence as the empty argument.

        The template's macros take a fixed number of arguments, so an absent
        value becomes ``{}`` — never the string ``None``.
        """
        if value is None or not value.strip():
            return ""
        return self._text(value, entity_id, field)

    def _require_entries(self, entries: List, field: str, section: str) -> None:
        """
        Raise when a section the template wraps in a list environment is empty.

        The template opens the environment itself, so an empty section would
        emit ``\\begin{itemize}`` with no ``\\item`` and fail to compile.
        """
        if not entries:
            raise RenderingError(
                "{}: the section is empty, but the template's {} list "
                "environment cannot be rendered without at least one "
                "entry.".format(field, section)
            )

    # ------------------------------------------------------------------
    # Escaping
    # ------------------------------------------------------------------

    def _text(self, value: str, entity_id: str, field: str) -> str:
        """
        Escape a value for LaTeX body text, then transliterate.

        Escaping runs *first*. Several transliterations emit LaTeX markup of
        their own (``\\ldots{}``, ``$\\bullet$``), and escaping afterwards would
        turn that markup into literal backslashes and braces.
        """
        escaped = _ESCAPE_RE.sub(lambda match: _ESCAPES[match.group(0)], value)
        return self._to_ascii(escaped, entity_id, field)

    def _url(self, value: str, entity_id: str, field: str) -> str:
        """
        Escape a value for use inside ``\\href``'s first argument.

        Escaping a URL with the body-text escaper is the classic way to corrupt
        a link: ``_`` and ``&`` are ordinary URL characters and must survive.
        """
        escaped = _URL_ESCAPE_RE.sub(
            lambda match: _URL_ESCAPES[match.group(0)], value
        )
        return self._to_ascii(escaped, entity_id, field)

    def _to_ascii(self, value: str, entity_id: str, field: str) -> str:
        """
        Transliterate known punctuation, then refuse anything still non-ASCII.

        Dropping or substituting an unknown character would corrupt content
        silently, which is worse than failing here.
        """
        characters = []  # type: List[str]
        for character in value:
            if character in _TRANSLITERATIONS:
                characters.append(_TRANSLITERATIONS[character])
            elif ord(character) < 128:
                characters.append(character)
            else:
                raise RenderingError(
                    "{}.{}: the character {!r} (U+{:04X}) has no LaTeX "
                    "representation in this template and would be corrupted "
                    "silently.".format(entity_id, field, character, ord(character))
                )
        return "".join(characters)
