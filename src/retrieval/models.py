"""
The structured result of Knowledge Base retrieval.

Task 020 §14: "the Planner receives structured canonical candidates rather than
searching files itself." This is that structure.

It records **what was considered as well as what was chosen**. A retrieval
result listing only the winners cannot answer the question a report most needs
to answer — "the Knowledge Base holds an AI project; did this run look at it
and pass, or never see it?" — so every scored entity appears, carrying its
score, the job terms it matched, and whether it was selected.

Deterministic by construction: no timestamps, no durations, no random ids, and
every list built in a defined order rather than from set iteration. The same
Knowledge Base and the same ``JobAnalysis`` must produce an equal object, for
the same reason ``QualityGateResult`` and ``RevisionResult`` must.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class RetrievedEntity(BaseModel):
    """One Knowledge Base entity, scored against the job."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str
    kind: str
    label: str
    score: float
    matched_terms: List[str] = []
    selected: bool = False


class RetrievedHighlight(BaseModel):
    """
    One canonical highlight, scored against the job.

    ``duplicate_of`` is set when the highlight was passed over because a
    higher-scoring one already said the same thing. That is a different outcome
    from simply not making the cut, and the Reporter says so — otherwise a
    canonical fact looks dropped when it was deliberately deduplicated.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str
    entity_id: str
    text: str
    score: float
    selected: bool = False
    duplicate_of: Optional[str] = None


class KnowledgeBaseRetrieval(BaseModel):
    """Everything retrieval decided, in a form the Planner and Reporter can read."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    summary_id: str
    summaries: List[RetrievedEntity] = []
    experiences: List[RetrievedEntity] = []
    projects: List[RetrievedEntity] = []
    skill_categories: List[RetrievedEntity] = []
    education: List[RetrievedEntity] = []
    highlights: List[RetrievedHighlight] = []
    supporting_evidence: List[str] = []

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def selected_ids(self, kind: str) -> List[str]:
        """Return the ids selected for one entity kind, in selection order."""
        return [entity.id for entity in self._of_kind(kind) if entity.selected]

    def considered_but_not_selected(self, kind: str) -> List[RetrievedEntity]:
        """Return the entities of this kind that were scored and passed over."""
        return [entity for entity in self._of_kind(kind) if not entity.selected]

    def selected_highlights(self, entity_id: str) -> List[str]:
        """Return the highlight text selected for one entity, in order."""
        return [
            highlight.text
            for highlight in self.highlights
            if highlight.entity_id == entity_id and highlight.selected
        ]

    def duplicates_dropped(self) -> List[RetrievedHighlight]:
        """Return every highlight passed over as a restatement of another."""
        return [h for h in self.highlights if h.duplicate_of is not None]

    def _of_kind(self, kind: str) -> List[RetrievedEntity]:
        return {
            "experience": self.experiences,
            "project": self.projects,
            "skill_category": self.skill_categories,
            "education": self.education,
            "summary": self.summaries,
        }.get(kind, [])
