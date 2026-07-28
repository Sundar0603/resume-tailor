"""
Doctor command for Resume Tailor.

Verifies that the AI provider stack is correctly configured and reachable.

On first run, guides the user through provider selection and configuration.
On subsequent runs, loads the saved configuration and runs a smoke test.

The CLI communicates exclusively with:
    - ConfigManager
    - CredentialManager
    - ProviderFactory

It never touches HTTP, SDKs, or API keys directly.
"""

from __future__ import annotations

from typing import Optional

import typer

from src.config.credentials import CredentialManager
from src.config.exceptions import ConfigError
from src.config.manager import ConfigManager
from src.config.models import ProviderType, ResumeTailorConfig
from src.providers.base import (
    AuthenticationError,
    ConnectionError,
    ProviderError,
    ProviderResponseError,
    RateLimitError,
)
from src.providers.factory import ProviderFactory

# ---------------------------------------------------------------------------
# Smoke-test prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a diagnostic endpoint.\n\n"
    "Reply with exactly:\n\n"
    "Resume Tailor is working."
)

_USER_PROMPT = (
    "Reply with exactly:\n\n"
    "Resume Tailor is working."
)

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_header() -> None:
    typer.echo("")
    typer.echo("Resume Tailor Doctor")
    typer.echo("")


def _print_success(message: str) -> None:
    typer.echo(f"\u2713 {message}")


def _print_failure(message: str) -> None:
    typer.echo(f"\u2717 {message}")


def _print_section(title: str) -> None:
    typer.echo("")
    typer.echo(title)
    typer.echo("")


def _provider_display_name(provider: ProviderType) -> str:
    """Return a human-readable display name for a provider."""
    return provider.value.capitalize()


# ---------------------------------------------------------------------------
# First-time setup
# ---------------------------------------------------------------------------


def _run_setup(
    config_manager: ConfigManager,
    credential_manager: CredentialManager,
) -> ResumeTailorConfig:
    """
    Interactively guide the user through first-time provider configuration.

    Returns the newly created and persisted :class:`ResumeTailorConfig`.
    """
    typer.echo("No AI provider is configured.")
    typer.echo("")
    typer.echo("Let's configure Resume Tailor.")
    typer.echo("")

    # --- Provider selection (driven by the registry, no hardcoding) ---
    providers = ProviderFactory.available_providers()

    typer.echo("Select AI Provider")
    typer.echo("")
    for idx, provider in enumerate(providers, start=1):
        typer.echo(f"  {idx}. {_provider_display_name(provider)}")
    typer.echo("")

    while True:
        raw = typer.prompt("Enter number").strip()
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(providers):
                selected_provider = providers[choice - 1]
                break
        typer.echo(f"  Please enter a number between 1 and {len(providers)}.")

    typer.echo("")

    # --- Collect fields required by the selected provider ---
    fields = ProviderFactory.required_fields(selected_provider)

    collected: dict = {}
    for field in fields:
        is_optional = "(optional)" in field.lower()
        label = field.replace(" (optional)", "").strip()
        is_secret = label.lower() == "api_key"

        if is_optional:
            value: Optional[str] = typer.prompt(
                f"  {label} (optional, press Enter to skip)",
                default="",
                show_default=False,
            ).strip() or None
        elif is_secret:
            value = typer.prompt(f"  {label}", hide_input=True).strip()
        else:
            value = typer.prompt(f"  {label}").strip()

        collected[label] = value

    typer.echo("")

    # --- Build config from collected values ---
    api_key: Optional[str] = collected.pop("api_key", None)
    model: str = collected.pop("model", "")
    # host covers both "host" (Ollama) and "base_url" (OpenAI optional)
    host: Optional[str] = collected.pop("host", None) or collected.pop("base_url", None)

    config = ResumeTailorConfig(
        provider=selected_provider,
        model=model,
        host=host if host else None,
    )

    # --- Persist config and credentials ---
    config_manager.save(config)
    _print_success("Configuration saved")

    if api_key:
        credential_manager.save(selected_provider, api_key)
        _print_success("Credentials stored securely")

    return config


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _run_smoke_test(
    config: ResumeTailorConfig,
    credential_manager: CredentialManager,
) -> None:
    """
    Construct the provider via ProviderFactory and send the diagnostic prompt.

    Prints the result or a user-friendly error message.
    """
    typer.echo(f"Provider : {_provider_display_name(config.provider)}")
    typer.echo(f"Model    : {config.model}")
    typer.echo("")
    typer.echo("Testing connection...")
    typer.echo("")

    try:
        provider = ProviderFactory.create(config, credential_manager)
        response = provider.generate(
            prompt=_USER_PROMPT,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except AuthenticationError as exc:
        _print_failure("Failed to connect")
        _print_section("Reason")
        typer.echo(f"  {exc}")
        typer.echo("")
        typer.echo("Verify that:")
        typer.echo("  \u2022 The API key is correct")
        typer.echo("  \u2022 The key has not expired or been revoked")
        raise typer.Exit(code=1)
    except ConnectionError as exc:
        _print_failure("Failed to connect")
        _print_section("Reason")
        typer.echo(f"  {exc}")
        typer.echo("")
        typer.echo("Verify that:")
        typer.echo(f"  \u2022 {_provider_display_name(config.provider)} is running")
        typer.echo("  \u2022 The configured host is reachable")
        if config.provider == ProviderType.OLLAMA:
            typer.echo("  \u2022 The model is installed")
        raise typer.Exit(code=1)
    except RateLimitError as exc:
        _print_failure("Failed to connect")
        _print_section("Reason")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except ProviderResponseError as exc:
        _print_failure("Failed to connect")
        _print_section("Reason")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)
    except ProviderError as exc:
        _print_failure("Failed to connect")
        _print_section("Reason")
        typer.echo(f"  {exc}")
        raise typer.Exit(code=1)

    _print_success("Connected successfully")
    _print_section("Model Response")
    typer.echo(f"  {response.strip()}")
    typer.echo("")
    typer.echo("All checks passed.")
    typer.echo("")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@app.command()
def doctor(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        help="Override the default configuration file path.",
        hidden=True,
    ),
) -> None:
    """
    Verify that Resume Tailor is correctly configured and can reach the AI provider.
    """
    from pathlib import Path

    _print_header()

    config_manager = ConfigManager(
        config_path=Path(config_path) if config_path else None
    )
    credential_manager = CredentialManager()

    # --- Load or create configuration ---
    if config_manager.exists():
        try:
            config = config_manager.load()
        except ConfigError as exc:
            _print_failure("Failed to load configuration")
            typer.echo(f"  {exc}")
            raise typer.Exit(code=1)
        _print_success("Configuration loaded")
    else:
        typer.echo("No provider configured.")
        typer.echo("")
        typer.echo("Launching setup...")
        typer.echo("")
        try:
            config = _run_setup(config_manager, credential_manager)
        except typer.Abort:
            typer.echo("")
            typer.echo("Setup cancelled.")
            raise typer.Exit(code=1)

    typer.echo("")

    # --- Run smoke test ---
    _run_smoke_test(config, credential_manager)
