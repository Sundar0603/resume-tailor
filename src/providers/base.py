"""
Provider exceptions for Resume Tailor.

All provider-specific SDK exceptions are translated into these
project-level exceptions so that the analyzer and generator
never receive SDK-specific errors.
"""


class ProviderError(Exception):
    """Base exception for all provider-level failures."""


class AuthenticationError(ProviderError):
    """Raised when the provider rejects the API key or credentials."""


class ConnectionError(ProviderError):
    """Raised when the provider cannot be reached (network, host, timeout)."""


class RateLimitError(ProviderError):
    """Raised when the provider rate-limits the request."""


class ProviderResponseError(ProviderError):
    """Raised when the provider returns an unexpected or empty response."""
