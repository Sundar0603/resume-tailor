r"""
Protected facts: what must survive a compression, and how that is checked.

Deterministic, offline, and independent of the model. The task doc is explicit
that the prompt is not the mechanism — "the LLM response must never be trusted
solely because it followed the prompt" — so facts are extracted from the
original bullet in Python before the call, and verified against the reply in
Python afterwards.

**The technology lexicon comes from the resume itself.** ``PROJECT_KNOWLEDGE``
§11 records that "recognising 'this word is a technology' needs a lexicon the
project does not have", and for open-ended prose that is still true. For this
much narrower job it is not: the resume already names its own technologies in
``Experience.technologies``, ``Project.technologies``, the skills section and
the project names. A per-run lexicon built from those is precise, needs no
external data, and cannot go stale.

Two classes of fact, verified differently because they fail differently.

``numerics``
    Compared as **exact** strings, insensitive only to whitespace. ``40%`` may
    become neither ``50%`` nor ``40 percent``. The reverse is checked too: a
    number in the reply that was not in the original is a fabrication, which is
    the failure mode the task doc cares most about.
``terms``
    Compared **case-insensitively** after normalisation, with boundaries. That
    lets ``Reduced API Latency`` compress to ``cut API latency`` while still
    rejecting ``Redis`` becoming ``caching`` — the specific word is either
    there or it is not.

Erring toward over-extraction is deliberate: "when uncertain whether something
is a protected fact, prefer preserving it." The cost of an extra protected term
is a tighter compression; the cost of a missed one is a resume that quietly
lost the thing that made it credible.
"""

import re
from typing import Iterable, List, Sequence

from src.parser.models import Resume

from .models import ProtectedFacts

#: Numeric shapes, most specific first. Alternation order is load-bearing:
#: ``40%`` must match the percentage branch before the bare-integer branch
#: reaches the ``40``.
_NUMERIC_RE = re.compile(
    r"""
      (?: v \d+ (?: \. \d+ )+ )                     # v2.1
    | (?: \d+ (?:\.\d+)? \s? % )                    # 40%, 99.9%
    | (?: \d+ (?:\.\d+)? \s? \+ )                   # 500+
    | (?: \d+ (?:\.\d+)? \s? [xX] (?![A-Za-z]) )    # 3x
    | (?: \d+ (?:\.\d+)? \s?
          (?: ms|us|ns|GB|MB|KB|TB|gb|mb|kb|tb|hrs|hr|min|s|k|K|M )
          (?![A-Za-z]) )                            # 30 ms, 5k
    | (?: \d+ (?: \. \d+ )+ )                       # 2.0
    | (?: \d+ )                                     # 2025, 40
    """,
    re.VERBOSE,
)

#: A capitalised word that opens a sentence carries no signal, so runs are only
#: collected from the second token onward. These additionally never count even
#: mid-sentence: they are ordinary words that a model may capitalise for style.
_NEVER_A_NAMED_FACT = frozenset(
    [
        "i",
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "for",
        "with",
        "using",
        "built",
        "led",
        "designed",
        "developed",
        "reduced",
        "improved",
        "implemented",
        "created",
        "delivered",
        "managed",
        "automated",
        "optimised",
        "optimized",
    ]
)

#: Terms shorter than this are not protected. One- and two-character tokens
#: produce far more false matches than real technologies; ``Go`` is the known
#: casualty and is accepted, because protecting it would protect every "Go".
_MIN_TERM_LENGTH = 3


def build_lexicon(resume: Resume) -> List[str]:
    """
    Return every concrete term this resume names, longest first.

    Longest-first matters: ``Spring Boot`` must be recognised before ``Spring``
    so a compression that keeps only the latter is still rejected.
    """
    terms = []  # type: List[str]
    terms.extend(resume.all_skills())
    for experience in resume.experiences:
        terms.extend(experience.technologies)
        terms.extend(experience.domains)
    for project in resume.projects:
        terms.extend(project.technologies)
        terms.extend(project.domains)
        terms.append(project.name)

    seen = set()
    unique = []  # type: List[str]
    for term in terms:
        cleaned = term.strip()
        if len(cleaned) < _MIN_TERM_LENGTH:
            continue
        key = _normalise(cleaned)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)

    return sorted(unique, key=lambda t: (-len(t), t.casefold()))


def extract_numerics(text: str) -> List[str]:
    """Return every numeric fact in ``text``, in order of appearance."""
    return [match.group(0).strip() for match in _NUMERIC_RE.finditer(text)]


def extract_named_facts(text: str) -> List[str]:
    """
    Return capitalised runs and acronyms that read as proper nouns.

    Catches concrete names the resume's own fields do not list — ``OAuth 2.0``,
    ``Model Context Protocol``, ``Triage Studio`` when it appears only in
    prose. The first token of the text is skipped: a sentence-initial capital
    carries no signal.

    Note the generator already lowercases mid-sentence *generic* vocabulary
    (``decapitalise_mid_sentence``), so a capital that survived that pass is
    good evidence of a real name.
    """
    tokens = text.split()
    facts = []  # type: List[str]
    run = []  # type: List[str]

    for position, token in enumerate(tokens):
        bare = token.strip(".,;:()[]").strip()
        if position > 0 and _looks_named(bare):
            run.append(bare)
            continue
        if len(run) >= 1:
            facts.append(" ".join(run))
        run = []

    if run:
        facts.append(" ".join(run))

    return [f for f in facts if len(f) >= _MIN_TERM_LENGTH]


def _looks_named(token: str) -> bool:
    """Return whether one bare token reads as part of a proper noun."""
    if not token or token.casefold() in _NEVER_A_NAMED_FACT:
        return False
    if not token[0].isalpha() or not token[0].isupper():
        # "2.0" continues a run it does not start; handled by the caller only
        # because a run already in progress absorbs it below.
        return _continues_a_run(token)
    return True


def _continues_a_run(token: str) -> bool:
    """
    Return whether a token may sit *inside* a named run without starting one.

    A version-like token: it carries digits and a dot. This is what keeps the
    ``2.0`` in ``OAuth 2.0`` attached to the name rather than stranded as a
    bare number.
    """
    return bool(token) and any(ch.isdigit() for ch in token) and "." in token


def extract_protected_facts(text: str, lexicon: Sequence[str]) -> ProtectedFacts:
    """
    Return everything in ``text`` that a compression must preserve unchanged.

    Parameters
    ----------
    text
        The original bullet.
    lexicon
        Terms this resume names, from :func:`build_lexicon`. Longest first.
    """
    numerics = _dedupe(extract_numerics(text))

    terms = [term for term in lexicon if contains_term(text, term)]
    for named in extract_named_facts(text):
        if not any(_normalise(named) in _normalise(t) for t in terms):
            terms.append(named)

    return ProtectedFacts(numerics=numerics, terms=_dedupe(terms))


def verify(facts: ProtectedFacts, compressed: str) -> List[str]:
    """
    Return every reason ``compressed`` fails to preserve ``facts``.

    An empty list means the compression is safe to apply. The engine rejects on
    anything non-empty and keeps the original bullet — a rejection is a normal
    outcome, not an error.
    """
    reasons = []  # type: List[str]

    for numeric in facts.numerics:
        if not contains_numeric(compressed, numeric):
            reasons.append("lost or altered numeric fact {0!r}".format(numeric))

    original_numerics = {_normalise_numeric(n) for n in facts.numerics}
    for numeric in extract_numerics(compressed):
        if _normalise_numeric(numeric) not in original_numerics:
            reasons.append("fabricated numeric fact {0!r}".format(numeric))

    for term in facts.terms:
        if not contains_term(compressed, term):
            reasons.append("lost or generalised term {0!r}".format(term))

    return reasons


def contains_term(haystack: str, term: str) -> bool:
    """
    Return whether ``term`` appears in ``haystack``, case-insensitively.

    Boundaries are "not a letter or digit" rather than ``\\b``, so terms
    carrying punctuation (``C++``, ``.NET``, ``Node.js``) match correctly.
    """
    pattern = r"(?<![0-9A-Za-z]){0}(?![0-9A-Za-z])".format(re.escape(term.strip()))
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def contains_numeric(haystack: str, numeric: str) -> bool:
    """
    Return whether ``numeric`` appears in ``haystack`` exactly.

    Whitespace-insensitive (``30 ms`` and ``30ms`` are the same fact) and
    guarded against a digit or decimal point immediately before, so ``40%``
    is not satisfied by ``140%``.
    """
    target = _normalise_numeric(numeric)
    flat = _normalise_numeric(haystack)
    pattern = r"(?<![0-9.]){0}".format(re.escape(target))
    return re.search(pattern, flat, re.IGNORECASE) is not None


def _normalise_numeric(value: str) -> str:
    """Strip every space so ``30 ms`` and ``30ms`` compare equal."""
    return re.sub(r"\s+", "", value)


def _normalise(value: str) -> str:
    """Casefold and collapse whitespace, for set membership only."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _dedupe(values: Iterable[str]) -> List[str]:
    """Return ``values`` with normalised duplicates dropped, order preserved."""
    seen = set()
    kept = []  # type: List[str]
    for value in values:
        key = _normalise(value)
        if key and key not in seen:
            seen.add(key)
            kept.append(value)
    return kept
