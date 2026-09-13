"""
Scoring a Knowledge Base entity against a job description.

Two weightings multiply together.

*How much the job cares* — a term in ``required_skills`` is worth more than one
scraped out of a responsibility sentence. The structured lists the Analyzer
extracts carry real signal; the prose fields carry whatever words the posting
happened to use, which is why they are weighted lowest and stripped of generic
software vocabulary first.

*Where the entity says it* — a term in ``technologies`` is a claim about what
the candidate works with; the same word inside a highlight may be incidental.

The product of the two is the entity's score. It is a ranking device and
nothing more: it decides what the Planner gets to consider, never what the
resume says. Every number below was chosen to express an ordering, and the
ordering is what the tests assert — no test depends on a specific total.
"""

from typing import Dict, List, Sequence, Tuple

from src.analyzer.models import JobAnalysis
from src.knowledge.models import CanonicalSummary
from src.parser.models import Education, Experience, Project, SkillCategory
from src.vocabulary import GENERIC_TERMS, contains_term, normalise

from .aliases import expand

#: How much a term is worth, by the ``JobAnalysis`` field it came from.
#: Structured fields outrank prose by design — see the module docstring.
JOB_FIELD_WEIGHTS = (
    ("required_skills", 3.0),
    ("technologies", 3.0),
    ("domains", 2.0),
    ("preferred_skills", 1.5),
    ("nice_to_have", 1.5),
    ("keywords", 1.0),
)

#: Prose fields, tokenised into single words and filtered. Weighted lowest
#: because a responsibility sentence contains far more words than claims.
JOB_PROSE_FIELDS = ("responsibilities", "qualifications")

#: Weight for a word recovered from prose.
PROSE_WEIGHT = 0.5

#: How much a match is worth, by the entity field it landed in.
ENTITY_FIELD_WEIGHTS = (
    ("technologies", 3.0),
    ("domains", 2.5),
    ("label", 2.0),
    ("highlights", 1.0),
)

#: Words too short to carry meaning when pulled out of prose one at a time.
_MIN_PROSE_WORD_LENGTH = 4


def job_terms(job_analysis: JobAnalysis) -> Dict[str, float]:
    """
    Return every term the job names, mapped to what a match on it is worth.

    Aliases are expanded here rather than at match time, so a job asking for
    "Large Language Models" scores an entity naming "LLM" at the full weight of
    the field the phrase came from.

    A term appearing in several fields keeps the **highest** weight it earned:
    something listed as both required and nice-to-have is required.
    """
    terms = {}  # type: Dict[str, float]

    def offer(value: str, weight: float) -> None:
        for alias in expand(value):
            if alias and terms.get(alias, 0.0) < weight:
                terms[alias] = weight

    for field, weight in JOB_FIELD_WEIGHTS:
        for value in getattr(job_analysis, field, None) or []:
            offer(value, weight)

    for field in JOB_PROSE_FIELDS:
        for sentence in getattr(job_analysis, field, None) or []:
            for word in _prose_words(sentence):
                offer(word, PROSE_WEIGHT)

    return terms


def _prose_words(sentence: str) -> List[str]:
    """
    Return the words in a prose sentence worth matching on.

    Generic software vocabulary is dropped using the same list the Generator
    uses to refuse an empty swap (``src/vocabulary.GENERIC_TERMS``). Without
    it, "development", "systems" and "quality" appear in nearly every posting
    and in nearly every resume bullet, so every entity scores alike and the
    ranking says nothing.
    """
    words = []  # type: List[str]
    for raw in normalise(sentence).replace("/", " ").split():
        word = raw.strip(".,;:()[]\"'")
        if len(word) < _MIN_PROSE_WORD_LENGTH or word in GENERIC_TERMS:
            continue
        words.append(word)
    return words


def score_fields(
    fields: Sequence[Tuple[str, Sequence[str]]], terms: Dict[str, float]
) -> Tuple[float, List[str]]:
    """
    Score one entity, given its fields and the job's weighted terms.

    Returns the total and the matched terms in a deterministic order (highest
    weight first, then alphabetical — never set iteration order, which would
    make the result non-reproducible between runs).

    Each term counts **once per field at most**, so an entity repeating
    "Python" across six highlights does not outrank one that genuinely spans
    six different technologies.
    """
    weights = dict(ENTITY_FIELD_WEIGHTS)
    total = 0.0
    matched = {}  # type: Dict[str, float]

    for field_name, values in fields:
        field_weight = weights.get(field_name, 1.0)
        haystack = " \n ".join(value for value in values if value)
        if not haystack:
            continue
        for term, term_weight in terms.items():
            if contains_term(haystack, term):
                total += term_weight * field_weight
                if matched.get(term, 0.0) < term_weight:
                    matched[term] = term_weight

    ordered = sorted(matched.items(), key=lambda pair: (-pair[1], pair[0]))
    return round(total, 4), [term for term, _ in ordered]


# ---------------------------------------------------------------------------
# Field projections, one per entity kind
# ---------------------------------------------------------------------------


def experience_fields(experience: Experience) -> List[Tuple[str, Sequence[str]]]:
    """Return the scorable fields of an experience."""
    return [
        ("technologies", experience.technologies),
        ("domains", experience.domains),
        ("label", [experience.role]),
        ("highlights", experience.highlights),
    ]


def project_fields(project: Project) -> List[Tuple[str, Sequence[str]]]:
    """Return the scorable fields of a project."""
    return [
        ("technologies", project.technologies),
        ("domains", project.domains),
        ("label", [project.name]),
        ("highlights", project.highlights),
    ]


def skill_category_fields(category: SkillCategory) -> List[Tuple[str, Sequence[str]]]:
    """
    Return the scorable fields of a skill category.

    The skills themselves are scored as ``technologies``: a skill entry is a
    claim about a tool, which is exactly what that weight is for.
    """
    return [
        ("technologies", category.skills),
        ("label", [category.category]),
    ]


def summary_fields(summary: CanonicalSummary) -> List[Tuple[str, Sequence[str]]]:
    """Return the scorable fields of a summary variant."""
    return [("highlights", [summary.text])]


def education_fields(degree: Education) -> List[Tuple[str, Sequence[str]]]:
    """Return the scorable fields of a degree."""
    return [("label", [degree.degree, degree.major])]


def highlight_fields(text: str) -> List[Tuple[str, Sequence[str]]]:
    """Return the scorable fields of one highlight sentence."""
    return [("highlights", [text])]
