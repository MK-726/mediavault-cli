"""Typer application entry point (FR-200–FR-209).

Phase 1 scope: --version and --help only. Subcommands are added in later
phases (§11). The app callback runs logging setup once, before any
command executes.
"""

from __future__ import annotations

import typer

from mediavault import __version__
from mediavault.logging_setup import configure_logging, get_logger

app = typer.Typer(
    name="mediavault-cli",
    help="Scan, catalogue, and analyze a local movie/show library.",
    # bare invocation will later open the menu (FR-200)
    no_args_is_help=False,
    add_completion=False,
)

_log = get_logger("cli")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mediavault-cli {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """MediaVault CLI."""
    # Pre-parse setup lives here (see §7). For now: logging only.
    # Config loading arrives with the config module (Phase 1 remainder).
    configure_logging(level="INFO", log_dir=None)
    _log.debug("mediavault-cli %s starting", __version__)


if __name__ == "__main__":  # pragma: no cover
    app()
