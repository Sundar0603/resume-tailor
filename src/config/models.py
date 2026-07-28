"""
Configuration models for Resume Tailor.

Defines the provider enumeration and the top-level configuration model.
Only non-sensitive configuration is stored here.
API keys are never included.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ProviderType(str, Enum):
    """
    Enumeration of supported AI providers.

    Using str as a mixin ensures the value is used directly
    when serializing to TOML.
    """

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class ResumeTailorConfig(BaseModel):
    """
    Top-level configuration model for Resume Tailor.

    Stores only non-sensitive configuration.
    API keys must never appear here.

    Attributes
    ----------
    provider : ProviderType
        The AI provider to use.
    model : str
        The model identifier to use with the provider.
    host : str | None
        Optional host URL, required for local providers such as Ollama.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    provider: ProviderType
    model: str
    host: Optional[str] = None

    @field_validator("model")
    @classmethod
    def model_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be empty")
        return value
