"""
Exceptions for the Job Description Analyzer.
"""


class AnalyzerError(Exception):
    """Base exception for all analyzer errors."""


class InvalidAnalyzerResponse(AnalyzerError):
    """Raised when the LLM provider returns an unexpected or empty response."""


class InvalidAnalyzerJSON(AnalyzerError):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class JobAnalysisValidationError(AnalyzerError):
    """Raised when the parsed JSON fails Pydantic schema validation."""
