"""
Synonym expansion — what makes deterministic retrieval *semantic*.

Task 020 §13 asks that retrieval "consider semantic relevance rather than
requiring exact string matches". The obvious way to buy that is a model call.
This project already spends 67-80 s of a 180 s budget on five of them, and the
Analyzer and Planner are deterministic by decision (PROJECT_KNOWLEDGE §9), so
a sixth call would cost real budget and surrender reproducibility for a job
that does not need either.

Almost all the semantic distance that matters here is *vocabulary*: a job
posting says "Large Language Models" where the resume says "LLM", or "Vue.js"
where the skills section says "Vue". A small bidirectional map closes that gap
exactly, costs nothing, and is inspectable — when a retrieval result looks
wrong, the reason is a line in this file rather than a sampling temperature.

**Kept deliberately small and specific.** Every entry is a genuine naming
variant of one thing. Loose "related concept" entries (``security`` ↔
``cybersecurity`` ↔ ``infosec``) are not here: they would make every entity
match every job, which is indistinguishable from no retrieval at all. The
failure mode of a missing alias is one entity ranked lower than it deserves;
the failure mode of a sloppy one is the ranking ceasing to mean anything.
"""

from typing import Dict, FrozenSet, Iterable, Set

from src.vocabulary import normalise

#: Groups of strings naming the same thing. Expansion is bidirectional: any
#: member of a group matches any other, so order within a group is irrelevant.
ALIAS_GROUPS = (
    # AI and agents
    ("llm", "llms", "large language model", "large language models"),
    ("mcp", "model context protocol"),
    ("rag", "retrieval augmented generation", "retrieval-augmented generation"),
    ("nlp", "natural language processing"),
    ("genai", "gen ai", "generative ai"),
    ("ai", "artificial intelligence"),
    ("ai agent", "ai agents", "agentic", "agentic systems", "agentic workflows"),
    ("prompt engineering", "prompting"),
    # Web and languages
    ("vue", "vue.js", "vuejs"),
    ("js", "javascript"),
    ("ts", "typescript"),
    ("node", "node.js", "nodejs"),
    ("rest", "restful", "rest api", "rest apis", "restful api", "restful apis"),
    ("api", "apis"),
    # Backend and data
    ("postgres", "postgresql"),
    ("k8s", "kubernetes"),
    ("ci/cd", "cicd", "continuous integration", "continuous delivery"),
    ("oauth", "oauth 2.0", "oauth2"),
    ("jwt", "json web token", "json web tokens"),
    # Security
    ("soc", "security operations center", "security operations centre"),
    ("siem", "security information and event management"),
    ("ioc", "iocs", "indicator of compromise", "indicators of compromise"),
    ("tip", "threat intelligence platform"),
    ("incident response", "ir"),
    ("cdp", "chrome devtools protocol"),
)


def _build_index() -> Dict[str, FrozenSet[str]]:
    """Map each normalised alias to every member of its group."""
    index = {}  # type: Dict[str, FrozenSet[str]]
    for group in ALIAS_GROUPS:
        members = frozenset(normalise(member) for member in group)
        for member in members:
            # A term appearing in two groups takes the union of both, so the
            # map cannot depend on group order.
            index[member] = index.get(member, frozenset()) | members
    return index


#: Normalised alias -> every normalised name for the same thing.
ALIAS_INDEX = _build_index()


def expand(term: str) -> Set[str]:
    """
    Return ``term`` together with every other name for the same thing.

    >>> sorted(expand("LLM"))
    ['large language model', 'large language models', 'llm', 'llms']
    >>> sorted(expand("Redis"))
    ['redis']
    """
    key = normalise(term)
    if not key:
        return set()
    return set(ALIAS_INDEX.get(key, frozenset([key]))) | {key}


def expand_all(terms: Iterable[str]) -> Set[str]:
    """Return the union of :func:`expand` over every term."""
    expanded = set()  # type: Set[str]
    for term in terms:
        expanded |= expand(term)
    return expanded
