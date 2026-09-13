"""
Turning a retrieval result into a ``Resume`` the existing chain already accepts.

This is the hinge of the whole task. The Planner, Generator, Validator, Renderer
and Revision Engine all speak ``Resume``; teaching each of them a new
"KnowledgeBase plus retrieval" vocabulary would mean touching every stage and
re-earning every guarantee they currently hold. Instead retrieval ends by
assembling a perfectly ordinary ``Resume`` made **entirely of canonical
entities**, and the rest of the pipeline is unchanged.

The consequence worth stating plainly, because it is what keeps task 020 §20
satisfied: ``ResumeValidator.validate(source_resume=...)`` keeps its exact
meaning. The source is still a resume of human-verified facts. It is simply
assembled for this job rather than read off whichever file the user picked.
Nothing is weakened and no rule is relaxed.

**Knowledge Base ids are carried through as the runtime ids.** They already
have the ``{prefix}_{number}`` shape the rest of the project expects,
``mint_id`` derives new ids from the highest existing number so a gap is
harmless, and keeping them means a finished report can name the canonical fact
a bullet came from. The alternative — renumbering positionally — would throw
that lineage away at the first stage.
"""

from typing import List

from src.knowledge.models import KnowledgeBase
from src.parser.models import Metadata, Resume

from .models import KnowledgeBaseRetrieval


def build_source_resume(
    knowledge_base: KnowledgeBase, retrieval: KnowledgeBaseRetrieval
) -> Resume:
    """
    Assemble the canonical source resume for this run.

    Every entity is deep-copied out of the Knowledge Base, so the pipeline
    cannot mutate canonical data through the object it is handed. That is the
    mechanism behind "the Knowledge Base is a read-only input during
    tailoring": it is unreachable, not merely un-written-to.
    """
    summary = knowledge_base.summary(retrieval.summary_id)

    return Resume(
        metadata=Metadata(
            resume=knowledge_base.metadata.knowledge_base,
            template=knowledge_base.metadata.template,
            version=knowledge_base.metadata.version,
        ),
        contact=knowledge_base.contact.model_copy(deep=True),
        summary=summary.text if summary else "",
        skills=_skills(knowledge_base, retrieval),
        experiences=_experiences(knowledge_base, retrieval),
        projects=_projects(knowledge_base, retrieval),
        education=[degree.model_copy(deep=True) for degree in knowledge_base.education],
    )


def _skills(
    knowledge_base: KnowledgeBase, retrieval: KnowledgeBaseRetrieval
) -> List:
    """Return the selected skill categories, most relevant first."""
    categories = []
    for category_id in retrieval.selected_ids("skill_category"):
        category = knowledge_base.skill_category(category_id)
        if category is not None:
            categories.append(category.model_copy(deep=True))
    return categories


def _experiences(
    knowledge_base: KnowledgeBase, retrieval: KnowledgeBaseRetrieval
) -> List:
    """
    Return every experience, in Knowledge Base order, with a trimmed bullet pool.

    **Order is load-bearing and must stay Knowledge Base order.** The Validator
    compares experiences against the source *positionally*
    (``validator.py:333``), and a resume reads reverse-chronologically
    regardless of what any job description wants. The Generator deliberately
    never reorders them either (PROJECT_KNOWLEDGE §10b); this is the same rule
    one stage earlier.

    Highlights *within* an experience are reordered — they are ranked by
    relevance and cut to a budget. That is safe and is the point: the Knowledge
    Base holds twenty bullets for one job, written for four different resumes.
    """
    experiences = []
    for experience in knowledge_base.experiences:
        selected = retrieval.selected_highlights(experience.id)
        copied = experience.model_copy(deep=True)
        # An experience with no scored highlights keeps its own, rather than
        # arriving empty: the Validator requires non-empty highlights and the
        # renderer cannot open an empty itemize (PROJECT_KNOWLEDGE §10d).
        copied.highlights = selected or list(experience.highlights)
        experiences.append(copied)
    return experiences


def _projects(
    knowledge_base: KnowledgeBase, retrieval: KnowledgeBaseRetrieval
) -> List:
    """Return the selected projects, most relevant first."""
    projects = []
    for project_id in retrieval.selected_ids("project"):
        project = knowledge_base.project(project_id)
        if project is None:
            continue
        copied = project.model_copy(deep=True)
        selected = retrieval.selected_highlights(project.id)
        copied.highlights = selected or list(project.highlights)
        projects.append(copied)
    return projects
