"""
Strict-mode fabrication checks.

The ResumeValidator compares structure and immutable fields. It cannot tell
whether "Kubernetes" was in the source resume or invented by the model, because
technologies and skills are mutable by design. That gap is what this module
closes.

Strict mode promises the candidate that nothing on the tailored resume is a
claim they did not already make. Enforcing that in the prompt alone is not
enforcement — a prompt cannot be tested, and a model that ignores it fails
silently. So the same rule is checked in Python afterwards, and a violation
raises.

This is a heuristic, not a proof. It catches the two failure modes that matter:
a technology or skill appearing from nowhere, and a metric appearing from
nowhere. It cannot detect a fabricated *responsibility* phrased entirely in
words the resume already uses, and it does not try to.
"""

import re
from typing import Iterable, List, Set

from src.parser.models import Resume

from .exceptions import GenerationConstraintError

#: Matches a number with optional thousands separators, decimals, and a
#: trailing percent sign: 40, 1,200, 99.9, 40%.
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

#: Split prose into comparable word tokens.
_WORD_PATTERN = re.compile(r"[A-Za-z0-9+#./-]+")

#: Numbers small enough to appear naturally in rewritten prose regardless of
#: the source ("three services" becoming "3 services", "2 years"). Flagging
#: these produces more false positives than it prevents fabrications.
_TRIVIAL_NUMBERS = frozenset({"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"})


def source_vocabulary(resume: Resume) -> Set[str]:
    """
    Return every term the source resume can be said to support.

    Built case-insensitively from the structured term fields — technologies,
    domains, skills — plus every word appearing in the summary and in any
    highlight. Prose is included because a technology is often named in a
    bullet without being listed in the skills section.
    """
    vocabulary: Set[str] = set()

    for category in resume.skills:
        vocabulary.add(_normalise(category.category))
        vocabulary.update(_normalise(skill) for skill in category.skills)

    for experience in resume.experiences:
        vocabulary.update(_normalise(term) for term in experience.technologies)
        vocabulary.update(_normalise(term) for term in experience.domains)
        vocabulary.update(_words(experience.highlights))
        vocabulary.add(_normalise(experience.role))

    for project in resume.projects:
        vocabulary.update(_normalise(term) for term in project.technologies)
        vocabulary.update(_normalise(term) for term in project.domains)
        vocabulary.update(_words(project.highlights))
        vocabulary.add(_normalise(project.name))

    vocabulary.update(_words([resume.summary]))
    vocabulary.discard("")
    return vocabulary


def source_numbers(resume: Resume) -> Set[str]:
    """Return every numeric token appearing anywhere in the source resume."""
    numbers: Set[str] = set()
    for text in _all_prose(resume):
        numbers.update(_normalise_number(match) for match in _NUMBER_PATTERN.findall(text))
    return numbers


def enforce_strict(source: Resume, generated: Resume) -> None:
    """
    Raise if the generated resume introduces facts the source does not support.

    Parameters
    ----------
    source:
        The canonical resume.
    generated:
        The resume produced by the Generator.

    Raises
    ------
    GenerationConstraintError
        On the first unsupported term or number found. The message names the
        offending value and where it appeared, so a failed generation is
        diagnosable without re-running it.
    """
    vocabulary = source_vocabulary(source)
    _check_terms(generated, vocabulary)
    _check_numbers(source, generated)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_terms(generated: Resume, vocabulary: Set[str]) -> None:
    """Every named technology, domain and skill must be in the vocabulary."""
    for category in generated.skills:
        for skill in category.skills:
            _require_supported(skill, vocabulary, f"skill category {category.id}")

    for experience in generated.experiences:
        for term in experience.technologies:
            _require_supported(term, vocabulary, f"experience {experience.id}")
        for term in experience.domains:
            _require_supported(term, vocabulary, f"experience {experience.id}")

    for project in generated.projects:
        for term in project.technologies:
            _require_supported(term, vocabulary, f"project {project.id}")
        for term in project.domains:
            _require_supported(term, vocabulary, f"project {project.id}")


def _check_numbers(source: Resume, generated: Resume) -> None:
    """Every metric in the generated prose must appear in the source prose."""
    allowed = source_numbers(source) | _TRIVIAL_NUMBERS

    for text, where in _located_prose(generated):
        for raw in _NUMBER_PATTERN.findall(text):
            number = _normalise_number(raw)
            if number in allowed:
                continue
            raise GenerationConstraintError(
                "Strict mode forbids introducing metrics that are not in the "
                f"source resume: {raw!r} appears in {where} but nowhere in the "
                "source."
            )


def _require_supported(term: str, vocabulary: Set[str], where: str) -> None:
    """Raise unless the term, or every word in it, is supported by the source."""
    normalised = _normalise(term)
    if not normalised or normalised in vocabulary:
        return

    # A compound term is supported when its parts are: "React Native" is fine
    # when both "React" and "Native" appear, and "CI/CD pipelines" is fine when
    # the resume mentions "CI/CD".
    parts = _WORD_PATTERN.findall(normalised)
    if parts and all(part in vocabulary for part in parts):
        return

    raise GenerationConstraintError(
        "Strict mode forbids introducing technologies or skills that are not "
        f"in the source resume: {term!r} appears in {where} but nowhere in the "
        "source."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise(value: str) -> str:
    """Lowercase and collapse whitespace for case-insensitive comparison."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


def _normalise_number(value: str) -> str:
    """Drop thousands separators so 1,200 and 1200 compare equal."""
    return value.replace(",", "")


def _words(texts: Iterable[str]) -> Set[str]:
    """Return the normalised word tokens across a group of strings."""
    tokens: Set[str] = set()
    for text in texts:
        if not isinstance(text, str):
            continue
        tokens.update(word.casefold() for word in _WORD_PATTERN.findall(text))
    return tokens


def _all_prose(resume: Resume) -> List[str]:
    """Return every free-text string in a resume."""
    texts: List[str] = [resume.summary]
    for experience in resume.experiences:
        texts.extend(experience.highlights)
    for project in resume.projects:
        texts.extend(project.highlights)
    return texts


def _located_prose(resume: Resume) -> List[tuple]:
    """Return every free-text string paired with a human-readable location."""
    located: List[tuple] = [(resume.summary, "the summary")]
    for experience in resume.experiences:
        for highlight in experience.highlights:
            located.append((highlight, f"experience {experience.id}"))
    for project in resume.projects:
        for highlight in project.highlights:
            located.append((highlight, f"project {project.id}"))
    return located
