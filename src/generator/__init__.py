"""
Resume Generator package.

Transforms a source resume into a tailored resume by following a ResumePlan.
Returns a ``Resume`` object — never Markdown, LaTeX, or PDF.
"""

from .canonical import (
    canonicalize_experiences,
    canonicalize_projects,
    canonicalize_summary,
)
from .constraints import enforce_strict, source_numbers, source_vocabulary
from .exceptions import (
    GenerationConstraintError,
    GeneratorError,
    GeneratorResponseValidationError,
    InvalidGeneratorJSON,
    InvalidGeneratorResponse,
)
from .generator import MIN_PROJECT_COUNT, ResumeGenerator
from .models import (
    ExperienceContent,
    ExperienceResponse,
    ProjectContent,
    ProjectResponse,
    SummaryResponse,
)
from .prompts import (
    build_experiences_prompt,
    build_projects_prompt,
    build_summary_prompt,
)
from .sampling import (
    GENERATOR_MAX_TOKENS,
    GENERATOR_NUM_CTX,
    GENERATOR_TEMPERATURE,
    GENERATOR_TOP_K,
    GENERATOR_TOP_P,
    generator_options,
)

__all__ = [
    # Orchestrator
    "ResumeGenerator",
    "MIN_PROJECT_COUNT",
    # Response models
    "SummaryResponse",
    "ExperienceContent",
    "ExperienceResponse",
    "ProjectContent",
    "ProjectResponse",
    # Prompts
    "build_summary_prompt",
    "build_experiences_prompt",
    "build_projects_prompt",
    # Sampling
    "generator_options",
    "GENERATOR_TEMPERATURE",
    "GENERATOR_TOP_K",
    "GENERATOR_TOP_P",
    "GENERATOR_NUM_CTX",
    "GENERATOR_MAX_TOKENS",
    # Canonicalisation
    "canonicalize_summary",
    "canonicalize_experiences",
    "canonicalize_projects",
    # Constraints
    "enforce_strict",
    "source_vocabulary",
    "source_numbers",
    # Exceptions
    "GeneratorError",
    "InvalidGeneratorResponse",
    "InvalidGeneratorJSON",
    "GeneratorResponseValidationError",
    "GenerationConstraintError",
]
