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


class MissingJobRole(JobAnalysisValidationError):
    """
    Raised when the analyzed job description carries no job title.

    A job description pasted from a careers page is often only the
    requirements and qualifications sections, with the title living in the
    page heading rather than the body. The model is instructed never to
    invent a role, so it correctly returns null, and the resulting Pydantic
    error names ``role`` without saying that the input is what is missing.
    This subclass exists so the CLI can say so.

    A subclass of :class:`JobAnalysisValidationError` because it is still a
    schema violation: callers catching the general case keep working.
    """
