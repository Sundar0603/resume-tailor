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
)
from .models import JobAnalysis
from .provider import LLMProvider
from .sampling import DETERMINISTIC_OPTIONS, deterministic_options

__all__ = [
    "JDAnalyzer",
    "JobAnalysis",
    "LLMProvider",
    "AnalyzerError",
    "InvalidAnalyzerJSON",
    "InvalidAnalyzerResponse",
    "JobAnalysisValidationError",
    "canonicalize",
    "DETERMINISTIC_OPTIONS",
    "deterministic_options",
]
