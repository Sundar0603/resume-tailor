"""
Exceptions for the configuration system.
"""


class ConfigError(Exception):
    """Base exception for all configuration errors."""


class ConfigNotFoundError(ConfigError):
    """Raised when the configuration file does not exist."""


class ConfigParseError(ConfigError):
    """Raised when the configuration file cannot be parsed as valid TOML."""


class ConfigValidationError(ConfigError):
    """Raised when the parsed configuration fails Pydantic schema validation."""
