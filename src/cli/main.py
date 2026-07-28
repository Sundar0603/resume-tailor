"""
Main CLI entry point for Resume Tailor.

Registers all sub-commands and exposes the top-level ``app`` used by
the ``resume-tailor`` console script.
"""

import warnings

import typer

# Suppress noisy third-party warnings that are irrelevant to the user.
# google-auth emits FutureWarnings on Python 3.9 (EOL notice).
# urllib3 v2 emits NotOpenSSLWarning on macOS (LibreSSL vs OpenSSL).
warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", message=".*LibreSSL.*")
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")

from src.cli.analyze import analyze
from src.cli.doctor import doctor

app = typer.Typer(
    name="resume-tailor",
    help="Resume Tailor — AI-powered resume tailoring.",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Resume Tailor — AI-powered resume tailoring."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


app.command("doctor")(doctor)
app.command("analyze")(analyze)


def main() -> None:
    """Console script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
