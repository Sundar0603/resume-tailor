"""
KnowledgeBaseParser — reads the Knowledge Base Markdown file.

The Knowledge Base uses the **same Markdown dialect** as ``content/*.md``, so
the existing section helpers in ``src/helpers/_section_utils.py`` do the
splitting and field extraction. That is deliberate: the person maintaining the
Knowledge Base already knows this format, and a second dialect would be a second
thing to keep in step.

Two things differ from :class:`src.parser.resume_parser.ResumeParser`:

1. **Ids are read, not assigned.** ``ResumeParser`` calls
   ``assign_sequential_ids`` and numbers entities by position, which is correct
   for a runtime id and wrong for a canonical one — inserting a project at the
   top would silently renumber every project after it, and last week's
   retrieval result would no longer mean what it said. Every Knowledge Base
   block therefore carries an explicit ``Id:`` line, and a missing or duplicate
   one is an error rather than something quietly repaired.

2. **Summaries are plural.** ``# Summaries`` holds one or more ``## Summary``
   blocks, each an identified canonical variant.

The parser reads a file and returns data. It never writes, and it has no
knowledge of job descriptions, retrieval or modes.
"""

import re
from pathlib import Path
from typing import Callable, Dict, List

import yaml

from src.entity_ids import (
    EDUCATION_PREFIX,
    EXPERIENCE_PREFIX,
    PROJECT_PREFIX,
    SKILL_PREFIX,
)
from src.helpers._section_utils import (
    get_list,
    get_scalar,
    split_sub_blocks,
    split_top_level_sections,
)
from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Project,
    SkillCategory,
)

from .exceptions import (
    DuplicateEntityId,
    KnowledgeBaseNotFoundError,
    MalformedEntityId,
    MissingEntityId,
    MissingKnowledgeSection,
    WrappedBullet,
)
from .identifiers import has_expected_prefix
from .models import (
    SUMMARY_PREFIX,
    CanonicalSummary,
    KnowledgeBase,
    KnowledgeMetadata,
)

#: The ``Id:`` field name, spelled once.
ID_FIELD = "Id"

#: Section headings the file must contain. Projects are required here although
#: they are optional on a resume: a Knowledge Base with no projects has nothing
#: for retrieval to choose between, which is the whole point of the thing.
_REQUIRED_SECTIONS = (
    ("contact", "Contact"),
    ("summaries", "Summaries"),
    ("skills", "Skills"),
    ("work experience", "Work Experience"),
    ("projects", "Projects"),
    ("education", "Education"),
)

#: Front-matter keys, all required.
_METADATA_FIELDS = ("knowledge_base", "template", "version")


class KnowledgeBaseParser:
    """Parses the Knowledge Base Markdown file into a :class:`KnowledgeBase`."""

    def parse(self, file_path: str) -> KnowledgeBase:
        """
        Read and parse the Knowledge Base at ``file_path``.

        Raises
        ------
        KnowledgeBaseNotFoundError
            If no file exists at that path.
        KnowledgeBaseError
            If the document violates the Knowledge Base schema.
        """
        path = Path(file_path)
        if not path.is_file():
            raise KnowledgeBaseNotFoundError(
                "Knowledge Base file not found: {0}".format(file_path)
            )
        return self.parse_string(path.read_text(encoding="utf-8"))

    def parse_string(self, raw: str) -> KnowledgeBase:
        """
        Parse a Knowledge Base document held in memory.

        Exists for the same reason ``ResumeParser.parse_string`` does: every
        step after the read already operates on a string, so tests and callers
        that hold the text need not go through disk.
        """
        metadata = self._parse_metadata(raw)
        sections = split_top_level_sections(_strip_front_matter(raw))

        for key, display in _REQUIRED_SECTIONS:
            if key not in sections:
                raise MissingKnowledgeSection(
                    "Required section '# {0}' not found in the Knowledge Base.".format(
                        display
                    )
                )

        return KnowledgeBase(
            metadata=metadata,
            contact=self._parse_contact(sections["contact"]),
            summaries=self._parse_summaries(sections["summaries"]),
            skills=self._parse_skills(sections["skills"]),
            experiences=self._parse_experiences(sections["work experience"]),
            projects=self._parse_projects(sections["projects"]),
            education=self._parse_education(sections["education"]),
        )

    # ------------------------------------------------------------------
    # Front matter
    # ------------------------------------------------------------------

    def _parse_metadata(self, raw: str) -> KnowledgeMetadata:
        """Parse the YAML front matter into a :class:`KnowledgeMetadata`."""
        data = yaml.safe_load(_front_matter(raw))
        if not isinstance(data, dict):
            raise MissingKnowledgeSection(
                "Knowledge Base front matter did not produce a mapping."
            )
        for field in _METADATA_FIELDS:
            if field not in data:
                raise MissingKnowledgeSection(
                    "Knowledge Base front matter is missing '{0}'.".format(field)
                )
        return KnowledgeMetadata(
            knowledge_base=str(data["knowledge_base"]),
            template=str(data["template"]),
            version=str(data["version"]),
        )

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _parse_contact(self, body: str) -> Contact:
        """Parse the five required contact fields."""
        values = {}
        for field, key in (
            ("name", "Name"),
            ("phone", "Phone"),
            ("email", "Email"),
            ("linkedin", "LinkedIn"),
            ("github", "GitHub"),
        ):
            value = get_scalar(body, key)
            if value is None:
                raise MissingKnowledgeSection(
                    "Contact is missing required field: '{0}'".format(key)
                )
            values[field] = value
        return Contact(**values)

    def _parse_summaries(self, body: str) -> List[CanonicalSummary]:
        """Parse every ``## Summary`` block into an identified variant."""
        blocks = split_sub_blocks(body, "Summary")
        if not blocks:
            raise MissingKnowledgeSection(
                "Summaries section contains no '## Summary' blocks."
            )

        summaries = []
        for index, block in enumerate(blocks, start=1):
            entity_id = _require_id(block, SUMMARY_PREFIX, "Summary", index)
            text = _prose_after_fields(block)
            if not text:
                raise MissingKnowledgeSection(
                    "Summary block {0} ('{1}') has no text.".format(index, entity_id)
                )
            summaries.append(
                CanonicalSummary(
                    id=entity_id,
                    label=get_scalar(block, "Label"),
                    text=text,
                    source=EntitySource.CANONICAL,
                )
            )
        _reject_duplicates(summaries, "summary")
        return summaries

    def _parse_skills(self, body: str) -> List[SkillCategory]:
        """Parse every ``## <Category>`` block into a SkillCategory."""
        categories = []
        for index, (name, block) in enumerate(_named_sub_blocks(body), start=1):
            entity_id = _require_id(block, SKILL_PREFIX, "Skill category", index)
            categories.append(
                SkillCategory(
                    id=entity_id,
                    category=name,
                    skills=_bullets(block),
                    source=EntitySource.CANONICAL,
                )
            )
        if not categories:
            raise MissingKnowledgeSection("Skills section contains no categories.")
        _reject_duplicates(categories, "skill category")
        return categories

    def _parse_experiences(self, body: str) -> List[Experience]:
        """Parse every ``## Experience`` block, highlights held as a full pool."""
        return _parse_blocks(
            body, "Experience", EXPERIENCE_PREFIX, self._experience, "experience"
        )

    def _parse_projects(self, body: str) -> List[Project]:
        """Parse every ``## Project`` block."""
        return _parse_blocks(body, "Project", PROJECT_PREFIX, self._project, "project")

    def _parse_education(self, body: str) -> List[Education]:
        """Parse every ``## Degree`` block."""
        return _parse_blocks(body, "Degree", EDUCATION_PREFIX, self._degree, "degree")

    # ------------------------------------------------------------------
    # Entity builders
    # ------------------------------------------------------------------

    def _experience(self, block: str, entity_id: str, index: int) -> Experience:
        """Build one Experience from its block."""
        fields = _require_scalars(
            block,
            ("Company", "Role", "Employment Type", "Duration"),
            "Experience",
            index,
        )
        highlights = _checked_list(block, "Highlights", "Experience", entity_id)
        if not highlights:
            raise MissingKnowledgeSection(
                "Experience block {0} ('{1}') has no Highlights.".format(
                    index, entity_id
                )
            )
        return Experience(
            id=entity_id,
            company=fields["Company"],
            role=fields["Role"],
            employment_type=fields["Employment Type"],
            duration=fields["Duration"],
            location=get_scalar(block, "Location"),
            technologies=_checked_list(block, "Technologies", "Experience", entity_id),
            domains=_checked_list(block, "Domains", "Experience", entity_id),
            highlights=highlights,
            source=EntitySource.CANONICAL,
        )

    def _project(self, block: str, entity_id: str, index: int) -> Project:
        """Build one Project from its block."""
        fields = _require_scalars(block, ("Name", "Type"), "Project", index)
        highlights = _checked_list(block, "Highlights", "Project", entity_id)
        if not highlights:
            raise MissingKnowledgeSection(
                "Project block {0} ('{1}') has no Highlights.".format(index, entity_id)
            )
        return Project(
            id=entity_id,
            name=fields["Name"],
            type=fields["Type"],
            repository=get_scalar(block, "Repository"),
            technologies=_checked_list(block, "Technologies", "Project", entity_id),
            domains=_checked_list(block, "Domains", "Project", entity_id),
            highlights=highlights,
            source=EntitySource.CANONICAL,
        )

    def _degree(self, block: str, entity_id: str, index: int) -> Education:
        """Build one Education entry from its block."""
        fields = _require_scalars(
            block, ("Institution", "Degree", "Major", "Duration"), "Degree", index
        )
        return Education(
            id=entity_id,
            institution=fields["Institution"],
            degree=fields["Degree"],
            major=fields["Major"],
            duration=fields["Duration"],
            cgpa=get_scalar(block, "CGPA"),
            location=get_scalar(block, "Location"),
            source=EntitySource.CANONICAL,
        )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _parse_blocks(
    body: str,
    heading: str,
    prefix: str,
    build: Callable,
    label: str,
) -> List:
    """Split a section, read each block's id, and build its entity."""
    entities = []
    for index, block in enumerate(split_sub_blocks(body, heading), start=1):
        entity_id = _require_id(block, prefix, heading, index)
        entities.append(build(block, entity_id, index))
    if not entities:
        raise MissingKnowledgeSection(
            "Section contains no '## {0}' blocks.".format(heading)
        )
    _reject_duplicates(entities, label)
    return entities


#: A bullet's continuation line: indented, non-blank, and not itself a bullet.
_CONTINUATION_PATTERN = re.compile(r"^[ \t]+(?![-*]\s)\S")


def _checked_list(block: str, key: str, kind: str, entity_id: str) -> List[str]:
    """
    Read a bullet list, refusing a wrapped bullet instead of truncating at it.

    ``get_list`` ends a list at the first non-bullet, non-blank line. For a
    wrapped bullet that line is the continuation, so the rest of the list is
    dropped and nothing says so — the resume simply ships with fewer facts.

    Every ``content/*.md`` bullet is already a single long line, so this forbids
    nothing the format allowed. It converts a silent loss into an error naming
    the field and the entity.
    """
    label = re.compile(r"^" + re.escape(key) + r":\s*$", re.MULTILINE | re.IGNORECASE)
    match = label.search(block)
    if match:
        started = False
        for line in block[match.end():].splitlines():
            if line.strip().startswith("- "):
                started = True
                continue
            if not line.strip():
                continue
            if started and _CONTINUATION_PATTERN.match(line):
                raise WrappedBullet(
                    "{0} '{1}' wraps a '{2}' bullet onto a continuation line: "
                    "{3!r}. Keep each bullet on one line — a wrapped bullet "
                    "silently discards every bullet after it.".format(
                        kind, entity_id, key, line.strip()[:60]
                    )
                )
            break
    return get_list(block, key)


def _require_id(block: str, prefix: str, kind: str, index: int) -> str:
    """
    Return the block's declared id, raising when it is absent or malformed.

    Deliberately strict. A Knowledge Base id is a promise that this fact can be
    referred to by the same name tomorrow, and inventing one for a block that
    forgot to declare it would break that promise silently.
    """
    entity_id = get_scalar(block, ID_FIELD)
    if entity_id is None:
        raise MissingEntityId(
            "{0} block {1} has no '{2}:' line. Knowledge Base ids are declared, "
            "never derived from position.".format(kind, index, ID_FIELD)
        )
    entity_id = entity_id.strip()
    if not has_expected_prefix(entity_id, prefix):
        raise MalformedEntityId(
            "{0} block {1} declares id '{2}'; expected the form '{3}_001'.".format(
                kind, index, entity_id, prefix
            )
        )
    return entity_id


def _require_scalars(
    block: str, keys: tuple, kind: str, index: int
) -> Dict[str, str]:
    """Return every named scalar, raising on the first one missing."""
    values = {}
    for key in keys:
        value = get_scalar(block, key)
        if value is None:
            raise MissingKnowledgeSection(
                "{0} block {1} missing required field: '{2}'".format(kind, index, key)
            )
        values[key] = value
    return values


def _reject_duplicates(entities: List, label: str) -> None:
    """Raise when two entities of the same kind share an id."""
    seen = set()
    for entity in entities:
        if entity.id in seen:
            raise DuplicateEntityId(
                "Two {0} entries share the Knowledge Base id '{1}'.".format(
                    label, entity.id
                )
            )
        seen.add(entity.id)


def _named_sub_blocks(body: str) -> List:
    """
    Split a section on ``## <anything>``, returning (heading, block) pairs.

    Skill categories are named by their heading rather than by a ``Name:``
    field, so they cannot use :func:`split_sub_blocks`, which splits on a known
    heading. Mirrors ``SkillsParser``'s own approach.
    """
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    pairs = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        pairs.append((match.group(1).strip(), body[start:end].strip()))
    return pairs


def _bullets(block: str) -> List[str]:
    """Return every ``- `` bullet in a block, in order."""
    items = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


#: Field lines a summary block may carry. Everything else in the block is prose.
_SUMMARY_FIELDS = ("Id", "Label")

_SUMMARY_FIELD_PATTERN = re.compile(
    r"^(?:{0}):\s".format("|".join(_SUMMARY_FIELDS)), re.IGNORECASE
)


def _prose_after_fields(block: str) -> str:
    """
    Return the block's prose: every line that is not one of its known fields.

    Keyed on the *named* fields rather than on "anything shaped like Key:
    value". A summary is ordinary English and may legitimately contain a colon
    — "Comfortable on both sides: building and hardening" — and a general
    pattern would silently swallow that sentence as a field line.

    A bare ``---`` is a visual separator between blocks, not content, and is
    dropped for the same reason ``SummaryParser`` drops it. Without this the
    separator is appended to the summary and travels into the rendered PDF.
    """
    lines = [
        line.strip()
        for line in block.splitlines()
        if line.strip()
        and line.strip() != "---"
        and not _SUMMARY_FIELD_PATTERN.match(line.strip())
    ]
    return " ".join(lines).strip()


def _front_matter(raw: str) -> str:
    """Return the YAML text between the opening and closing ``---``."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise MissingKnowledgeSection(
            "Knowledge Base does not begin with YAML front matter ('---')."
        )
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index])
    raise MissingKnowledgeSection(
        "Knowledge Base front matter is not closed with '---'."
    )


def _strip_front_matter(raw: str) -> str:
    """Return the document body, with the leading YAML block removed."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return raw
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return raw
