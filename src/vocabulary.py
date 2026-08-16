"""
Shared vocabulary judgements about resume terms.

A resume's ``domains`` and ``technologies`` fields name subject matter and
tools. Job descriptions frequently describe a role entirely in process
language, and a model asked to align a resume with such a job will happily
write "Application Software Development" where "SOC Platforms" used to be —
trading a specific, credible fact for a phrase that says nothing.

This module decides when a proposed term is too general to be worth that
trade. It is deliberately lenient: a phrase is only rejected when *every*
significant word in it is generic. "SOC Automation" survives on "SOC",
"Sales Planning" survives on "Sales", and "Payments Platform" survives on
"Payments". Only a phrase with nothing specific left standing is refused.

The point is not to refuse job-description language. It is to refuse an
*empty swap*: replacing something concrete with something that could appear
on any software resume ever written. When a job genuinely names a domain —
"quota management", "territory design", "threat intelligence" — those pass,
and the tailoring goes ahead.
"""

import re
from typing import Iterable, Optional, Set

#: Words that carry no subject matter on a software resume. Every one of these
#: could appear on any engineering resume regardless of what the person
#: actually worked on, which is exactly what makes them useless as a domain.
#:
#: Kept deliberately short. Each addition makes the filter stricter, and a
#: false positive deletes a real domain while a false negative merely leaves a
#: vague one. Words that could anchor a genuine subject area are left out on
#: purpose: "design" ("API Design"), "automation" ("Workflow Automation"),
#: "deployment", "data", "workflow", "rule", "security", "caching".
GENERIC_TERMS = frozenset(
    {
        "app",
        "application",
        "applications",
        "architectural",
        "assurance",
        "code",
        "coding",
        "collaboration",
        "compliance",
        "debugging",
        "defect",
        "defects",
        "delivery",
        "development",
        "documentation",
        "engineering",
        "guideline",
        "guidelines",
        "handling",
        "issue",
        "issues",
        "lifecycle",
        "maintenance",
        "operations",
        "optimization",
        "practice",
        "practices",
        "principles",
        "process",
        "processes",
        "production",
        "profiling",
        "programming",
        "quality",
        "secure",
        "service",
        "services",
        "software",
        "standard",
        "standards",
        "support",
        "system",
        "systems",
        "test",
        "testing",
        "tests",
        "troubleshooting",
        "versioning",
    }
)

#: Grammatical filler that carries no meaning either way, so it neither saves
#: a phrase nor condemns it.
_STOPWORDS = frozenset({"a", "an", "and", "the", "of", "for", "in", "to", "with", "on"})

#: Splits a phrase into words, treating "/" and "&" as separators so
#: "Issue/Defect Collaboration" is judged on all three of its words.
_WORD_PATTERN = re.compile(r"[A-Za-z0-9+#.-]+")


def normalise(term: str) -> str:
    """Lowercase and collapse whitespace, for case-insensitive comparison."""
    if not isinstance(term, str):
        return ""
    return " ".join(term.split()).casefold()


def is_too_general(term: str) -> bool:
    """
    Return True when a term carries no subject matter of its own.

    True only when every significant word is generic. A single specific word
    anywhere in the phrase is enough to keep it.

    >>> is_too_general("Application Software Development")
    True
    >>> is_too_general("SOC Platforms")
    False
    """
    words = [w for w in _WORD_PATTERN.findall(normalise(term)) if w not in _STOPWORDS]
    if not words:
        return False
    return all(word in GENERIC_TERMS for word in words)


def normalised_set(terms: Iterable[str]) -> Set[str]:
    """Return a case-insensitive set of terms, for membership checks."""
    return {normalise(term) for term in terms if normalise(term)}


#: Head nouns that mark a phrase as an activity rather than a thing.
#:
#: This catches a different failure from :data:`GENERIC_TERMS`. That one
#: refuses a phrase with no specific word anywhere; this one refuses a phrase
#: that *is* specific but names something you do rather than something you know
#: — "Interoperability Strategies" is a perfectly precise phrase, and still not
#: a skill.
#:
#: Deliberately conservative, for the same reason: words that could head a real
#: skill are left out even when often misused — "architecture" ("Cloud
#: Architecture"), "testing" ("Load Testing"), "design" ("System Design"),
#: "profiling" ("Performance Profiling").
ACTIVITY_HEAD_NOUNS = frozenset(
    {
        "assurance",
        "criteria",
        "functionality",
        "handling",
        "improvement",
        "lifecycle",
        "maintenance",
        "methodologies",
        "methodology",
        "optimization",
        "practice",
        "practices",
        "principles",
        "process",
        "processes",
        "quality",
        "strategies",
        "strategy",
        "troubleshooting",
        "versioning",
    }
)

#: Single words that name a process, not a technology.
ACTIVITY_TERMS = frozenset({"sdlc"})


def looks_like_an_activity(term: str) -> bool:
    """
    Return True when a term names an activity rather than a thing.

    >>> looks_like_an_activity("Interoperability Strategies")
    True
    >>> looks_like_an_activity("Kubernetes")
    False
    """
    text = normalise(term)
    if not text:
        return False
    if text in ACTIVITY_TERMS:
        return True

    words = text.split()
    # A single word is usually a real technology ("Redis", "Kubernetes").
    # The failure mode is a capitalised multi-word phrase from a job posting.
    if len(words) < 2:
        return False

    # In an English phrase "A of B", the head is A: the subject of
    # "Optimization of Coding" is optimization, not coding. Without this the
    # last-word test reads the wrong end of the phrase.
    if " of " in text:
        head = text.split(" of ")[0].split()[-1]
    else:
        head = words[-1]

    return head in ACTIVITY_HEAD_NOUNS


#: Matches a run of consecutive capitalised words — "Code Quality",
#: "Application Software Development". Runs are handled as a unit: lowercasing
#: half of one leaves "system Design", which reads worse than leaving it alone.
_CAPITALISED_RUN = re.compile(r"[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*")

#: Characters after which a capital letter is correct.
_SENTENCE_ENDINGS = ".!?:"


def capitalised_runs(text: str) -> Set[str]:
    """
    Return the normalised capitalised phrases appearing in a piece of text.

    Used to collect the capitalisations the candidate chose themselves, so
    :func:`decapitalise_mid_sentence` leaves them alone.
    """
    if not isinstance(text, str):
        return set()
    return {normalise(run) for run in _CAPITALISED_RUN.findall(text) if run}


def decapitalise_mid_sentence(text: str, protected: Optional[Set[str]] = None) -> str:
    """
    Lowercase job-description process words capitalised mid-sentence.

    Models asked to work a job's vocabulary into prose tend to Capitalise it,
    producing "rigorous Software Testing and Code Quality assurance during
    Production Support" — which reads like a brochure rather than a resume.
    The prompts forbid it and the model complies inconsistently at a non-zero
    temperature, so it is corrected here.

    Only words in :data:`GENERIC_TERMS` are touched, which is what keeps this
    safe. A real proper noun is never in that set, so "Java", "Redis",
    "Terraform" and "Zoho" pass through untouched. Acronyms pass through too:
    an all-uppercase word like "API", "REST" or "OCI" is left exactly as
    written. A word beginning a sentence stays capitalised.

    ``protected`` holds capitalisations the candidate already used — collected
    from the source resume with :func:`capitalised_runs`. "Backend Software
    Engineer" and "Security Operations Center" contain generic words but are
    the candidate's own title-casing, and rewriting them is the same mistake as
    second-guessing their own skill wording.

    >>> decapitalise_mid_sentence("Ensured Code Quality across the API.")
    'Ensured code quality across the API.'
    """
    if not isinstance(text, str) or not text:
        return text

    allowed = protected or set()

    def protected_indices(words):
        """
        Indices covered by a protected phrase, by greedy longest match.

        A protected phrase is often only part of a run — "Seasoned Backend
        Software Engineer" contains "Backend Software Engineer" — so matching
        the run as a whole would miss it.
        """
        covered = set()
        index = 0
        while index < len(words):
            for end in range(len(words), index, -1):
                if normalise(" ".join(words[index:end])) in allowed:
                    covered.update(range(index, end))
                    index = end
                    break
            else:
                index += 1
        return covered

    def replace(match: "re.Match") -> str:
        run = match.group(0)
        words = run.split()
        keep = protected_indices(words) if allowed else set()
        if len(keep) == len(words):
            return run

        # An acronym is never a mistake: API, REST, OCI, SQL.
        plain = [
            w
            for i, w in enumerate(words)
            if not w.isupper() and i not in keep
        ]
        if not any(w.casefold() in GENERIC_TERMS for w in plain):
            return run

        preceding = text[: match.start()].rstrip()
        starts_sentence = not preceding or preceding[-1] in _SENTENCE_ENDINGS

        lowered = []
        for index, word in enumerate(words):
            if word.isupper() or index in keep or (index == 0 and starts_sentence):
                lowered.append(word)
            else:
                lowered.append(word[0].lower() + word[1:])
        return " ".join(lowered)

    return _CAPITALISED_RUN.sub(replace, text)


def is_weak_term(term: str) -> bool:
    """
    Return True when a term is not worth putting on a resume.

    The union of the two tests, which catch different things: a phrase can be
    too general ("Application Software Development" — nothing specific in it)
    or an activity ("Interoperability Strategies" — specific, but names doing
    rather than knowing). Both belong in reasoning and in highlight prose, not
    in a skills, technologies, or domains field.
    """
    return looks_like_an_activity(term) or is_too_general(term)
