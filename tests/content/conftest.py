"""
Fixtures for the content-data tests.

Unlike every other suite, these tests read the real ``content/*.md`` files
rather than a factory fixture. That is the point: the source resumes are hand
maintained data, and a wrong value there survives every downstream test because
the parser, the renderer and the compiler all treat it as truth. The checks
here are the only place that data is held to an invariant.
"""

import re
from pathlib import Path
from typing import List, Set

from src.parser.models import Project, Resume
from src.parser.resume_parser import ResumeParser

#: Repository root — ``tests/content/conftest.py`` is two directories down.
CONTENT_DIRECTORY = Path(__file__).resolve().parents[2] / "content"

#: Tokens too generic to prove a slug belongs to a project name.
_NOISE_TOKENS = frozenset({"app", "the", "and", "for", "project", "repo"})

#: A slug token must be this long before it counts as evidence of ownership.
_MIN_TOKEN_LENGTH = 3


def content_files() -> List[Path]:
    """Return every source resume, sorted, so test ids stay stable."""
    return sorted(CONTENT_DIRECTORY.glob("*_resume.md"))


def load_resume(path: Path) -> Resume:
    """Parse one source resume off disk."""
    return ResumeParser().parse(str(path))


def repository_slug(url: str) -> str:
    """
    Return the repository name from a URL — the last non-empty path segment.

    ``https://github.com/owner/triage-studio`` becomes ``triage-studio``. A URL
    with no path at all yields an empty string, which no name can match.
    """
    without_query = url.split("?", 1)[0].split("#", 1)[0]
    segments = [segment for segment in without_query.split("/") if segment]
    return segments[-1] if segments else ""


def significant_tokens(text: str) -> Set[str]:
    """
    Return the lowercase word tokens of ``text`` worth matching on.

    Punctuation and separators split; tokens shorter than
    ``_MIN_TOKEN_LENGTH`` and generic filler are dropped, because matching on
    ``a`` or ``app`` would let any slug claim any project.
    """
    tokens = re.split(r"[^A-Za-z0-9]+", text.lower())
    return {
        token
        for token in tokens
        if len(token) >= _MIN_TOKEN_LENGTH and token not in _NOISE_TOKENS
    }


def slug_matches_name(url: str, name: str) -> bool:
    """
    Return whether a repository URL plausibly belongs to a project name.

    Ownership is evidenced by a shared significant token between the project
    name and the repository slug. ``Triage Studio`` and ``triage-studio`` share
    two; ``Triage Studio`` and ``Daily-Studies`` share none, which is exactly
    the defect this rule exists to catch.
    """
    return bool(significant_tokens(repository_slug(url)) & significant_tokens(name))


def linked_projects(resume: Resume) -> List[Project]:
    """Return the projects in ``resume`` that carry a repository URL."""
    return [project for project in resume.projects if project.repository]


def project_link_targets(latex: str) -> List[str]:
    """
    Return the URL of every project "Link" anchor in a rendered document.

    Only project links are collected. The contact line also emits ``\\href``,
    but those anchors read ``LinkedIn``/``GitHub`` rather than the
    ``\\underline{Link}`` the project block uses, and they are not repository
    URLs to begin with.
    """
    pattern = re.compile(
        r"\\href\{([^}]*)\}\{\\color\{blue\}\\underline\{Link\}\}"
    )
    return pattern.findall(latex)
