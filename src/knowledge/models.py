"""
Domain models for the Knowledge Base.

The Knowledge Base is the canonical source of truth for career facts. It holds
every experience, project, skill, summary and degree the candidate can honestly
claim, independent of which role-specific resume happens to present them.

**These models deliberately reuse the parser's domain models.** An experience in
the Knowledge Base is a ``src.parser.models.Experience``, not a parallel type.
Task 020 §10 is explicit about this: a second incompatible schema would have to
be kept in step with the first forever, and every downstream stage already
speaks the existing vocabulary.

The one genuinely new concept is :class:`CanonicalSummary`. ``Resume.summary`` is
a required plain string, and the four role-specific resumes each carry a
different one. Keeping only a single summary would discard three canonical
pieces of writing, so the Knowledge Base holds them as identified variants and
retrieval picks the best-matching one as the base a run rewrites.

Nothing here is ever written by the pipeline. The Knowledge Base is a read-only
input during tailoring, and every entity it yields is
``EntitySource.CANONICAL`` by construction.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)

#: Id prefix for a canonical summary variant. The other four prefixes are the
#: parser's own (``skill``, ``exp``, ``proj``, ``edu``) and live in
#: ``src/entity_ids.py``; summaries have no runtime counterpart because a
#: ``Resume`` carries exactly one summary and it needs no id.
SUMMARY_PREFIX = "sum"


class KnowledgeMetadata(BaseModel):
    """Front matter of the Knowledge Base file."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    knowledge_base: str
    template: str
    version: str


class CanonicalSummary(BaseModel):
    """
    One canonical summary variant.

    ``label`` is a human note about when the variant applies ("backend
    emphasis"). It is never sent to a model and never rendered — it exists so
    the file stays readable to the person maintaining it.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str
    source: EntitySource = EntitySource.CANONICAL
    label: Optional[str] = None
    text: str

    def word_count(self) -> int:
        """Return the number of whitespace-separated words in the summary."""
        return len(self.text.split())


class KnowledgeBase(BaseModel):
    """
    Every canonical career fact, in one place.

    The four role-specific resumes under ``content/`` are curated *views* of
    this. They remain on disk and remain useful, but they are no longer
    authoritative, and a fact's absence from any one of them says nothing about
    whether it is canonical.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    metadata: KnowledgeMetadata
    contact: Contact
    summaries: List[CanonicalSummary] = []
    skills: List[SkillCategory] = []
    experiences: List[Experience] = []
    projects: List[Project] = []
    education: List[Education] = []

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def experience(self, entity_id: str) -> Optional[Experience]:
        """Return the experience with this Knowledge Base id, or None."""
        return _by_id(self.experiences, entity_id)

    def project(self, entity_id: str) -> Optional[Project]:
        """Return the project with this Knowledge Base id, or None."""
        return _by_id(self.projects, entity_id)

    def skill_category(self, entity_id: str) -> Optional[SkillCategory]:
        """Return the skill category with this Knowledge Base id, or None."""
        return _by_id(self.skills, entity_id)

    def summary(self, entity_id: str) -> Optional[CanonicalSummary]:
        """Return the summary variant with this Knowledge Base id, or None."""
        return _by_id(self.summaries, entity_id)

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def total_skills(self) -> int:
        """Return the total number of individual canonical skills."""
        return sum(category.skill_count() for category in self.skills)

    def total_highlights(self) -> int:
        """Return every canonical highlight across experiences and projects."""
        return sum(len(e.highlights) for e in self.experiences) + sum(
            len(p.highlights) for p in self.projects
        )

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    def as_resume(self) -> Resume:
        """
        Return the whole Knowledge Base as a single ``Resume``.

        **This is not a resume anyone would send.** It holds every experience
        bullet, every project and every skill at once, and would fail the
        Validator's ceilings on sight. It exists for one job: to be the factual
        *universe* strict mode is measured against (task 020 §18).

        Before the Knowledge Base, strict mode's vocabulary came from whichever
        role-specific resume was selected, so a genuine fact sitting in another
        file counted as invention. Passing this object as the universe is what
        makes strict mode able to reuse the AI work that only ever appeared on
        the cybersecurity resume — without loosening a single rule, because
        every term in here is canonical and human-verified.

        Returns a deep copy, so a caller cannot reach through it and mutate the
        Knowledge Base.
        """
        return Resume(
            metadata=Metadata(
                resume=self.metadata.knowledge_base,
                template=self.metadata.template,
                version=self.metadata.version,
            ),
            contact=self.contact.model_copy(deep=True),
            summary=self.summaries[0].text if self.summaries else "",
            skills=[c.model_copy(deep=True) for c in self.skills],
            experiences=[e.model_copy(deep=True) for e in self.experiences],
            projects=[p.model_copy(deep=True) for p in self.projects],
            education=[e.model_copy(deep=True) for e in self.education],
        )


def _by_id(entities: List, entity_id: str) -> Optional[object]:
    """Return the first entity carrying this id, or None."""
    for entity in entities:
        if entity.id == entity_id:
            return entity
    return None
