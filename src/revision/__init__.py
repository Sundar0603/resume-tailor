"""
Revision / Shortening Engine package.

Takes a generated resume that failed the Quality Gate and shortens it until it
passes, working on ``Resume`` objects and re-rendering through the frozen
template — never by editing ``resume.tex``.

Deterministic deletion is exhausted first, in the authoritative order
Projects -> Skills -> Experience (Internship -> Full-Time), never below the
retention floors in :mod:`src.revision.floors`. Only when no legal removal
remains and the page still overflows may a single consolidated LLM call
compress selected two-line bullets, and every fact in those bullets is
extracted and re-verified in Python on either side of it.

If one page cannot be reached without breaching a floor, the engine raises.
It never returns the original failing resume as a success.
"""

from .compression import (
    apply_compressions,
    eligible_bullets,
    evaluate_response,
    parse_response,
    select_candidates,
)
from .deletion import apply_removal, freeable_lines, next_removal, removal_plan
from .exceptions import (
    InvalidCompressionJSON,
    InvalidCompressionResponse,
    OnePageInfeasibleError,
    RevisionError,
    RevisionStateError,
)
from .facts import (
    build_lexicon,
    extract_named_facts,
    extract_numerics,
    extract_protected_facts,
    verify,
)
from .floors import (
    FULLTIME_BULLET_FLOOR,
    INTERNSHIP_BULLET_FLOOR,
    MIN_PROJECTS,
    MIN_TOTAL_SKILLS,
    PROJECT_BULLET_FLOOR,
    PROTECTED_SKILL_CATEGORIES,
    REQUIRED_EXPERIENCES,
    check_invariants,
    is_internship,
)
from .measure import (
    ONE_LINE_CHAR_BUDGET,
    ONE_LINE_WORD_BUDGET,
    bullet_id,
    estimated_lines,
    estimated_resume_lines,
    is_two_line_bullet,
    shortfall,
    word_count,
)
from .models import (
    BulletRef,
    CompressionCandidate,
    CompressionOutcome,
    EntityKind,
    ProtectedFacts,
    RemovalStep,
    RevisionAction,
    RevisionReason,
    RevisionResult,
    RevisionStep,
)
from .prompts import build_compression_prompt, response_markers
from .revision_engine import (
    DEFAULT_JOB_NAME,
    DEFAULT_OUTPUT_DIRECTORY,
    MAX_COMPRESSION_PASSES,
    MAX_DETERMINISTIC_STEPS,
    RevisionEngine,
)
from .sampling import compression_options

__all__ = [
    # Engine
    "RevisionEngine",
    "DEFAULT_OUTPUT_DIRECTORY",
    "DEFAULT_JOB_NAME",
    "MAX_COMPRESSION_PASSES",
    "MAX_DETERMINISTIC_STEPS",
    # Results and models
    "RevisionResult",
    "RevisionStep",
    "RevisionAction",
    "RevisionReason",
    "RemovalStep",
    "BulletRef",
    "EntityKind",
    "ProtectedFacts",
    "CompressionCandidate",
    "CompressionOutcome",
    # Floors
    "MIN_PROJECTS",
    "PROJECT_BULLET_FLOOR",
    "MIN_TOTAL_SKILLS",
    "PROTECTED_SKILL_CATEGORIES",
    "INTERNSHIP_BULLET_FLOOR",
    "FULLTIME_BULLET_FLOOR",
    "REQUIRED_EXPERIENCES",
    "is_internship",
    "check_invariants",
    # Deletion
    "next_removal",
    "apply_removal",
    "removal_plan",
    "freeable_lines",
    # Measurement
    "estimated_lines",
    "is_two_line_bullet",
    "estimated_resume_lines",
    "shortfall",
    "word_count",
    "bullet_id",
    "ONE_LINE_CHAR_BUDGET",
    "ONE_LINE_WORD_BUDGET",
    # Facts
    "build_lexicon",
    "extract_numerics",
    "extract_named_facts",
    "extract_protected_facts",
    "verify",
    # Compression
    "eligible_bullets",
    "select_candidates",
    "parse_response",
    "evaluate_response",
    "apply_compressions",
    "build_compression_prompt",
    "response_markers",
    "compression_options",
    # Exceptions
    "RevisionError",
    "OnePageInfeasibleError",
    "InvalidCompressionResponse",
    "InvalidCompressionJSON",
    "RevisionStateError",
]
