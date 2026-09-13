"""
KnowledgeBaseRetriever — finds the canonical facts a job description needs.

This is the stage task 020 introduces between understanding a job and planning a
resume. Its entire responsibility is stated in §12:

    Find canonical Knowledge Base entities relevant to the current Job
    Description.

And what it must not do is stated just as plainly: it does not generate, does
not rewrite, does not make final resume decisions, does not render and does not
compile. It reads a :class:`~src.knowledge.models.KnowledgeBase` and a
:class:`~src.analyzer.models.JobAnalysis`, and returns a ranked selection.

**No LLM call, by decision.** Deterministic scoring over the Analyzer's already
structured output costs nothing against a 180-second budget that five model
calls have most of, it is reproducible, and every ranking is explainable from a
weight table and an alias list rather than from a sample. See
``src/retrieval/aliases.py`` for why that is enough to count as semantic.

The Knowledge Base is read-only here and everywhere: every entity handed on is
a deep copy, so no stage downstream can reach back through the retrieval result
and mutate the canonical data.
"""

from typing import Callable, List, Sequence, Tuple

from src.analyzer.models import JobAnalysis
from src.knowledge.identifiers import highlight_id
from src.knowledge.models import KnowledgeBase

from . import scoring, selection
from .exceptions import EmptyKnowledgeBase, InsufficientCanonicalData
from .models import KnowledgeBaseRetrieval, RetrievedEntity, RetrievedHighlight


class KnowledgeBaseRetriever:
    """Selects the canonical entities relevant to one job description."""

    def retrieve(
        self, knowledge_base: KnowledgeBase, job_analysis: JobAnalysis
    ) -> KnowledgeBaseRetrieval:
        """
        Return the canonical entities relevant to ``job_analysis``.

        Parameters
        ----------
        knowledge_base
            The canonical source of truth. Never mutated.
        job_analysis
            The Analyzer's structured reading of the job description.

        Raises
        ------
        EmptyKnowledgeBase
            If there is nothing to retrieve from.
        InsufficientCanonicalData
            If the Knowledge Base cannot meet the Validator's floors.
        """
        self._guard(knowledge_base)
        terms = scoring.job_terms(job_analysis)

        summaries = self._rank(
            knowledge_base.summaries,
            "summary",
            lambda s: s.label or s.text[:60],
            scoring.summary_fields,
            terms,
        )
        experiences = self._rank(
            knowledge_base.experiences,
            "experience",
            lambda e: "{0} — {1}".format(e.company, e.role),
            scoring.experience_fields,
            terms,
        )
        projects = self._rank(
            knowledge_base.projects,
            "project",
            lambda p: p.name,
            scoring.project_fields,
            terms,
        )
        categories = self._rank(
            knowledge_base.skills,
            "skill_category",
            lambda c: c.category,
            scoring.skill_category_fields,
            terms,
        )
        education = self._rank(
            knowledge_base.education,
            "education",
            lambda d: "{0}, {1}".format(d.degree, d.major),
            scoring.education_fields,
            terms,
        )

        # Experiences and education are never a choice. The Planner cannot add
        # or remove an experience and the Validator requires exactly two, so
        # ranking them decides nothing — it only explains the selection.
        for entity in experiences + education:
            entity.selected = True

        _select_top(summaries, 1)
        _select_top(projects, selection.MAX_PROJECTS)
        subsumed = _select_skill_categories(categories, knowledge_base)

        highlights = self._select_highlights(knowledge_base, projects, terms)

        return KnowledgeBaseRetrieval(
            summary_id=summaries[0].id,
            summaries=summaries,
            experiences=experiences,
            projects=projects,
            skill_categories=categories,
            education=education,
            highlights=highlights,
            supporting_evidence=_evidence(
                summaries, experiences, projects, categories, highlights, subsumed
            ),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _guard(self, knowledge_base: KnowledgeBase) -> None:
        """Refuse a Knowledge Base that cannot produce a valid resume."""
        if not (
            knowledge_base.experiences
            or knowledge_base.projects
            or knowledge_base.skills
        ):
            raise EmptyKnowledgeBase("The Knowledge Base holds no entities.")
        if not knowledge_base.summaries:
            raise InsufficientCanonicalData(
                "The Knowledge Base holds no summary; a resume requires one."
            )
        if len(knowledge_base.projects) < selection.MIN_PROJECTS:
            raise InsufficientCanonicalData(
                "The Knowledge Base holds {0} project(s); the Validator requires "
                "at least {1}.".format(
                    len(knowledge_base.projects), selection.MIN_PROJECTS
                )
            )
        if not knowledge_base.skills:
            raise InsufficientCanonicalData(
                "The Knowledge Base holds no skill categories."
            )
        if not knowledge_base.education:
            raise InsufficientCanonicalData(
                "The Knowledge Base holds no education entries."
            )

    def _rank(
        self,
        entities: Sequence,
        kind: str,
        label: Callable,
        fields: Callable,
        terms: dict,
    ) -> List[RetrievedEntity]:
        """
        Score every entity of one kind and return them best first.

        The tie-break is the Knowledge Base id, so two entities scoring equally
        always come back in the same order. Without it the ranking would depend
        on dictionary iteration and the same inputs could produce a different
        resume.
        """
        scored = []
        for entity in entities:
            score, matched = scoring.score_fields(fields(entity), terms)
            scored.append(
                RetrievedEntity(
                    id=entity.id,
                    kind=kind,
                    label=label(entity),
                    score=score,
                    matched_terms=matched,
                )
            )
        return sorted(scored, key=lambda e: (-e.score, e.id))

    def _select_highlights(
        self,
        knowledge_base: KnowledgeBase,
        projects: List[RetrievedEntity],
        terms: dict,
    ) -> List[RetrievedHighlight]:
        """
        Rank and select the highlights of every experience and selected project.

        Both are trimmed to a budget, because the pool holds every variant
        written for every role-specific resume — twenty bullets on one job,
        nine on one project. An unselected project gets a budget of zero: its
        highlights are still scored and still reported, so the record shows
        what was considered, but none is carried into the resume.
        """
        results = []  # type: List[RetrievedHighlight]

        for experience in knowledge_base.experiences:
            budget = selection.highlight_budget(experience.employment_type)
            results.extend(
                _rank_and_take(experience.id, experience.highlights, terms, budget)
            )

        selected_projects = {p.id for p in projects if p.selected}
        for project in knowledge_base.projects:
            budget = (
                selection.MAX_PROJECT_HIGHLIGHTS
                if project.id in selected_projects
                else 0
            )
            results.extend(
                _rank_and_take(project.id, project.highlights, terms, budget)
            )

        return results


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _rank_and_take(
    entity_id: str, highlights: Sequence[str], terms: dict, budget: int
) -> List[RetrievedHighlight]:
    """Score one entity's highlights, take the best, and record the rest."""
    scored = []  # type: List[Tuple[str, float]]
    for text in highlights:
        score, _matched = scoring.score_fields(scoring.highlight_fields(text), terms)
        scored.append((text, score))

    # Ties keep Knowledge Base order, which is the order a human wrote them in.
    ranked = sorted(scored, key=lambda pair: -pair[1])
    taken, rejected = selection.take_distinct(ranked, budget)

    duplicate_of = {text: original for text, original in rejected}
    chosen = set(taken)

    results = []
    for text, score in scored:
        original = duplicate_of.get(text)
        results.append(
            RetrievedHighlight(
                id=highlight_id(entity_id, text),
                entity_id=entity_id,
                text=text,
                score=score,
                selected=text in chosen,
                duplicate_of=(
                    highlight_id(entity_id, original) if original is not None else None
                ),
            )
        )
    return results


def _select_skill_categories(
    categories: List[RetrievedEntity], knowledge_base: KnowledgeBase
) -> List[str]:
    """
    Select the best categories, skipping any whose skills are already shown.

    The Knowledge Base is a merge of four resumes that each named their own
    categories, so it holds overlapping ones — "AI and Agentic Systems" and
    "AI and Automation", where the second is a strict subset of the first. A
    resume printing both headings reads as padding, and dropping the subsumed
    one loses no fact: every skill in it is already on the page.

    Same shape as the highlight duplicate guard: a skipped category does not
    consume the budget, so the next genuinely different one moves up.

    Returns the ids skipped, so the report can say why a canonical category
    did not appear rather than leaving it looking dropped. Only the ids are
    returned: a category is judged against the *union* of everything chosen
    ahead of it, so there is often no single category that covers it, and
    naming one would be a guess.
    """
    shown = set()
    skipped = []  # type: List[str]
    chosen = []  # type: List[RetrievedEntity]

    for entity in categories:
        if len(chosen) >= selection.MAX_SKILL_CATEGORIES:
            break
        category = knowledge_base.skill_category(entity.id)
        if category is None:
            continue
        if chosen and selection.is_subsumed(category.skills, shown):
            skipped.append(entity.id)
            continue
        entity.selected = True
        chosen.append(entity)
        shown |= selection.expanded_skills(category.skills)

    return skipped


def _select_top(entities: List[RetrievedEntity], budget: int) -> None:
    """Mark the best ``budget`` entities selected, in place."""
    for entity in entities[:budget]:
        entity.selected = True


def _evidence(
    summaries: List[RetrievedEntity],
    experiences: List[RetrievedEntity],
    projects: List[RetrievedEntity],
    categories: List[RetrievedEntity],
    highlights: List[RetrievedHighlight],
    subsumed: List[str],
) -> List[str]:
    """
    Return human-readable notes explaining the selection.

    Read by the Reporter and by anyone asking why a run used what it used.
    Prose, never parsed.
    """
    notes = []  # type: List[str]

    for group, kind in (
        (summaries, "summary"),
        (projects, "project"),
        (categories, "skill category"),
    ):
        for entity in group:
            if not entity.selected:
                continue
            notes.append(
                "selected {0} {1} ('{2}') at score {3} on: {4}".format(
                    kind,
                    entity.id,
                    entity.label,
                    entity.score,
                    ", ".join(entity.matched_terms[:6]) or "no direct term match",
                )
            )

    for entity in projects:
        if not entity.selected:
            notes.append(
                "considered project {0} ('{1}') at score {2} and did not select it".format(
                    entity.id, entity.label, entity.score
                )
            )

    for skipped_id in subsumed:
        notes.append(
            "skipped skill category {0}: every skill in it is already shown by "
            "a higher-ranked category".format(skipped_id)
        )

    for highlight in highlights:
        if highlight.duplicate_of is not None:
            notes.append(
                "dropped highlight {0} as a restatement of {1}".format(
                    highlight.id, highlight.duplicate_of
                )
            )

    return notes
