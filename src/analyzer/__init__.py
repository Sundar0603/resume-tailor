"""
Job Description Analyzer package.

Public API::

    from src.analyzer import JDAnalyzer, JobAnalysis
"""

from .analyzer import JDAnalyzer
from .canonical import canonicalize
from .exceptions import (
    AnalyzerError,
    InvalidAnalyzerJSON,
    InvalidAnalyzerResponse,
    JobAnalysisValidationError,
    MissingJobRole,
)
from .models import JobAnalysis
from .provider import LLMProvider
from .role_fallback import FALLBACK_ROLES, build_role_fallback_prompt, resolve_role
from .sampling import DETERMINISTIC_OPTIONS, deterministic_options

__all__ = [
    "JDAnalyzer",
    "JobAnalysis",
    "LLMProvider",
    "AnalyzerError",
    "InvalidAnalyzerJSON",
    "InvalidAnalyzerResponse",
    "JobAnalysisValidationError",
    "MissingJobRole",
    "FALLBACK_ROLES",
    "build_role_fallback_prompt",
    "resolve_role",
    "canonicalize",
    "DETERMINISTIC_OPTIONS",
    "deterministic_options",
]
