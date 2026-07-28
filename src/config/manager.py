"""
Configuration manager for Resume Tailor.

Responsible exclusively for filesystem operations on the configuration file.
Never stores or reads secrets.
"""

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .exceptions import ConfigNotFoundError, ConfigParseError, ConfigValidationError
from .models import ResumeTailorConfig

# Default location: ~/.resume-tailor/config.toml
_DEFAULT_CONFIG_DIR = Path.home() / ".resume-tailor"
_DEFAULT_CONFIG_PATH = _DEFAULT_CONFIG_DIR / "config.toml"


class ConfigManager:
    """
    Manages persistence of :class:`ResumeTailorConfig` to and from disk.

    The configuration is stored as TOML inside the user's home directory.
    Secrets are never written to or read from this file.

    Parameters
    ----------
    config_path : Path | None
        Override the default config path. Primarily used in tests.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path: Path = config_path if config_path is not None else _DEFAULT_CONFIG_PATH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        """Return True if the configuration file exists on disk."""
        return self._path.exists()

    def save(self, config: ResumeTailorConfig) -> None:
        """
        Persist *config* to disk as TOML.

        The parent directory is created automatically if it does not exist.

        Parameters
        ----------
        config : ResumeTailorConfig
            The configuration to persist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        toml_content = self._serialize(config)
        self._path.write_text(toml_content, encoding="utf-8")

    def load(self) -> ResumeTailorConfig:
        """
        Load and return the configuration from disk.

        Returns
        -------
        ResumeTailorConfig
            The loaded and validated configuration.

        Raises
        ------
        ConfigNotFoundError
            If the configuration file does not exist.
        ConfigParseError
            If the file cannot be parsed as valid TOML.
        ConfigValidationError
            If the parsed data fails schema validation.
        """
        if not self._path.exists():
            raise ConfigNotFoundError(
                f"Configuration file not found: {self._path}"
            )

        raw = self._path.read_text(encoding="utf-8")

        try:
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigParseError(
                f"Failed to parse configuration file: {exc}"
            ) from exc

        try:
            return ResumeTailorConfig(**data)
        except (ValidationError, TypeError) as exc:
            raise ConfigValidationError(
                f"Invalid configuration: {exc}"
            ) from exc

    def delete(self) -> None:
        """
        Delete the configuration file from disk.

        Does nothing if the file does not exist.
        """
        if self._path.exists():
            self._path.unlink()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(config: ResumeTailorConfig) -> str:
        """
        Serialize *config* to a TOML-formatted string.

        Uses manual serialization to avoid adding a tomlwrite dependency.
        The standard library ``tomllib`` is read-only, so we build the
        TOML string directly from the model fields.
        """
        lines: list[str] = []

        lines.append(f'provider = "{config.provider.value}"')
        lines.append(f'model = "{config.model}"')

        if config.host is not None:
            lines.append(f'host = "{config.host}"')

        return "\n".join(lines) + "\n"
