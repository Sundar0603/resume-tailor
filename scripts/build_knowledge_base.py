"""
Merge the four role-specific resumes into a draft Knowledge Base.

**Run once, by hand, then review the output before it becomes the real file.**
This is a migration aid, not part of any pipeline. Nothing in ``src/`` imports
it and no tailoring run ever executes it — task 020's hard boundary is that the
Knowledge Base is written by a human and read by the machine, never the reverse.

What it does, and why each choice was made:

*Experiences* are the same two jobs in all four resumes, described with
overlapping but different bullets. The union of those bullets is the canonical
pool. Exact duplicates (after whitespace normalisation) collapse; **near
duplicates are kept**, by explicit decision — the backend resume's "creating,
validating, versioning, and deploying" and the fullstack resume's "create,
edit, validate, and manage" describe the same platform but emphasise different
work, and choosing between them is a tailoring decision, not a migration one.
Retrieval scores them and a similarity guard stops both shipping together.

*Projects* merge by name, unioning technologies, domains and highlights.

*Skills* merge by category name, unioning the skills within each.

*Summaries* are kept as four identified variants; the file's own prose is the
thing being preserved, so none is discarded.

*Contact* is taken from ``--email``, because the four resumes disagree.

Usage
-----
    .venv/bin/python scripts/build_knowledge_base.py > knowledge/knowledge_base.md
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.entity_ids import (  # noqa: E402
    EDUCATION_PREFIX,
    EXPERIENCE_PREFIX,
    PROJECT_PREFIX,
    SKILL_PREFIX,
    format_id,
)
from src.knowledge.models import SUMMARY_PREFIX  # noqa: E402
from src.parser import ResumeParser  # noqa: E402
from src.vocabulary import normalise  # noqa: E402

#: The order resumes are merged in. First occurrence wins for ordering, so the
#: resume listed first sets the shape of the file and the rest add to it.
#: cybersecurity-ai leads because it is the richest — most skills, most
#: highlights, and the only one carrying the Resume Tailor project.
MERGE_ORDER = (
    "cybersecurity_ai_resume.md",
    "cybersecurity_resume.md",
    "backend_resume.md",
    "fullstack_resume.md",
)

#: Human note attached to each summary variant, keyed by source file.
SUMMARY_LABELS = {
    "cybersecurity_ai_resume.md": "cybersecurity and AI emphasis",
    "cybersecurity_resume.md": "cybersecurity emphasis",
    "backend_resume.md": "backend emphasis",
    "fullstack_resume.md": "full stack emphasis",
}


def merge(resumes: List[Tuple[str, object]]) -> Dict:
    """Union every canonical entity across the given resumes."""
    experiences: List = []
    projects: List = []
    skills: List = []
    education: List = []
    summaries: List = []

    for filename, resume in resumes:
        summaries.append((filename, resume.summary))
        _merge_experiences(experiences, resume.experiences)
        _merge_projects(projects, resume.projects)
        _merge_skills(skills, resume.skills)
        _merge_education(education, resume.education)

    return {
        "summaries": summaries,
        "skills": skills,
        "experiences": experiences,
        "projects": projects,
        "education": education,
    }


def _merge_experiences(target: List, incoming: List) -> None:
    """Merge experiences keyed on (company, role) — the same job, described differently."""
    for experience in incoming:
        key = (normalise(experience.company), normalise(experience.role))
        existing = _find(target, lambda e: (normalise(e.company), normalise(e.role)) == key)
        if existing is None:
            target.append(experience.model_copy(deep=True))
            continue
        existing.technologies = _union(existing.technologies, experience.technologies)
        existing.domains = _union(existing.domains, experience.domains)
        existing.highlights = _union(existing.highlights, experience.highlights)


def _merge_projects(target: List, incoming: List) -> None:
    """Merge projects keyed on name."""
    for project in incoming:
        existing = _find(target, lambda p: normalise(p.name) == normalise(project.name))
        if existing is None:
            target.append(project.model_copy(deep=True))
            continue
        existing.technologies = _union(existing.technologies, project.technologies)
        existing.domains = _union(existing.domains, project.domains)
        existing.highlights = _union(existing.highlights, project.highlights)
        existing.repository = existing.repository or project.repository


def _merge_skills(target: List, incoming: List) -> None:
    """Merge skill categories keyed on category name."""
    for category in incoming:
        existing = _find(
            target, lambda c: normalise(c.category) == normalise(category.category)
        )
        if existing is None:
            target.append(category.model_copy(deep=True))
            continue
        existing.skills = _union(existing.skills, category.skills)


def _merge_education(target: List, incoming: List) -> None:
    """Merge degrees keyed on (institution, degree)."""
    for degree in incoming:
        key = (normalise(degree.institution), normalise(degree.degree))
        if _find(target, lambda d: (normalise(d.institution), normalise(d.degree)) == key):
            continue
        target.append(degree.model_copy(deep=True))


def _find(items: List, predicate):
    """Return the first item satisfying ``predicate``, or None."""
    for item in items:
        if predicate(item):
            return item
    return None


def _union(existing: List[str], incoming: List[str]) -> List[str]:
    """
    Append whatever is new, preserving order and dropping exact duplicates.

    Exact means "identical once normalised", so a difference of whitespace or
    case does not create a second canonical entry. Anything genuinely reworded
    is kept — see the module docstring.
    """
    seen = {normalise(value) for value in existing}
    merged = list(existing)
    for value in incoming:
        if normalise(value) not in seen:
            merged.append(value)
            seen.add(normalise(value))
    return merged


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(merged: Dict, contact, email: str, template: str) -> str:
    """Render the merged data as a Knowledge Base Markdown document."""
    out: List[str] = []
    out.append("---")
    out.append("knowledge_base: sundar")
    out.append("template: {0}".format(template))
    out.append("version: 1.0")
    out.append("---")
    out.append("")
    out.append("# Contact")
    out.append("")
    for key, value in (
        ("Name", contact.name),
        ("Phone", contact.phone),
        ("Email", email),
        ("LinkedIn", contact.linkedin),
        ("GitHub", contact.github),
    ):
        out.append("{0}: {1}".format(key, value))
        out.append("")
    out.append("---")
    out.append("")

    out.append("# Summaries")
    out.append("")
    for index, (filename, text) in enumerate(merged["summaries"], start=1):
        out.append("## Summary")
        out.append("")
        out.append("Id: {0}".format(format_id(SUMMARY_PREFIX, index)))
        out.append("")
        label = SUMMARY_LABELS.get(filename)
        if label:
            out.append("Label: {0}".format(label))
            out.append("")
        out.append(text)
        out.append("")
        out.append("---")
        out.append("")

    out.append("# Skills")
    out.append("")
    for index, category in enumerate(merged["skills"], start=1):
        out.append("## {0}".format(category.category))
        out.append("")
        out.append("Id: {0}".format(format_id(SKILL_PREFIX, index)))
        out.append("")
        for skill in category.skills:
            out.append("- {0}".format(skill))
        out.append("")
        out.append("---")
        out.append("")

    out.append("# Work Experience")
    out.append("")
    for index, experience in enumerate(merged["experiences"], start=1):
        out.append("## Experience")
        out.append("")
        out.append("Id: {0}".format(format_id(EXPERIENCE_PREFIX, index)))
        out.append("")
        for key, value in (
            ("Company", experience.company),
            ("Role", experience.role),
            ("Employment Type", experience.employment_type),
            ("Location", experience.location),
            ("Duration", experience.duration),
        ):
            if value:
                out.append("{0}: {1}".format(key, value))
                out.append("")
        _render_list(out, "Technologies", experience.technologies)
        _render_list(out, "Domains", experience.domains)
        _render_list(out, "Highlights", experience.highlights, spaced=True)
        out.append("---")
        out.append("")

    out.append("# Projects")
    out.append("")
    for index, project in enumerate(merged["projects"], start=1):
        out.append("## Project")
        out.append("")
        out.append("Id: {0}".format(format_id(PROJECT_PREFIX, index)))
        out.append("")
        out.append("Name: {0}".format(project.name))
        out.append("")
        out.append("Type: {0}".format(project.type))
        out.append("")
        if project.repository:
            out.append("Repository: {0}".format(project.repository))
            out.append("")
        _render_list(out, "Technologies", project.technologies)
        _render_list(out, "Domains", project.domains)
        _render_list(out, "Highlights", project.highlights, spaced=True)
        out.append("---")
        out.append("")

    out.append("# Education")
    out.append("")
    for index, degree in enumerate(merged["education"], start=1):
        out.append("## Degree")
        out.append("")
        out.append("Id: {0}".format(format_id(EDUCATION_PREFIX, index)))
        out.append("")
        for key, value in (
            ("Institution", degree.institution),
            ("Degree", degree.degree),
            ("Major", degree.major),
            ("CGPA", degree.cgpa),
            ("Location", degree.location),
            ("Duration", degree.duration),
        ):
            if value:
                out.append("{0}: {1}".format(key, value))
                out.append("")
        out.append("---")
        out.append("")

    while out and out[-1] in ("", "---"):
        out.pop()
    return "\n".join(out) + "\n"


def _render_list(out: List[str], key: str, values: List[str], spaced: bool = False) -> None:
    """
    Emit a ``Key:`` label followed by its bullets.

    Each bullet is written on **one line however long it is**. Wrapping would
    silently truncate the list on the next parse (PROJECT_KNOWLEDGE §10c); the
    Knowledge Base parser now refuses a wrapped bullet outright, so a wrapped
    file would fail loudly rather than lose facts — but emitting them unwrapped
    is what keeps that from ever arising.
    """
    if not values:
        return
    out.append("{0}:".format(key))
    out.append("")
    for value in values:
        out.append("- {0}".format(" ".join(value.split())))
        if spaced:
            out.append("")
    if not spaced:
        out.append("")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-dir", default="content")
    parser.add_argument("--email", default="sundarselvam3@gmail.com")
    parser.add_argument("--template", default="default")
    args = parser.parse_args()

    resume_parser = ResumeParser()
    resumes = []
    for filename in MERGE_ORDER:
        path = Path(args.content_dir) / filename
        if not path.is_file():
            print("missing: {0}".format(path), file=sys.stderr)
            return 1
        resumes.append((filename, resume_parser.parse(str(path))))

    merged = merge(resumes)
    document = render(merged, resumes[0][1].contact, args.email, args.template)

    print(
        "merged {0} skill categories, {1} experiences, {2} projects, "
        "{3} degrees, {4} summaries".format(
            len(merged["skills"]),
            len(merged["experiences"]),
            len(merged["projects"]),
            len(merged["education"]),
            len(merged["summaries"]),
        ),
        file=sys.stderr,
    )
    sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
