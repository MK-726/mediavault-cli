"""Typer application entry point (FR-200–FR-209).

Phase 1 scope: --version and --help only. Subcommands are added in later
phases (§11). The app callback runs logging setup once, before any
command executes.
"""

from __future__ import annotations

import typer

from mediavault import __version__
from mediavault.config import load_config
from mediavault.errors import ConfigurationError
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
    try:
        config = load_config()
    except ConfigurationError as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(code=1)

    configure_logging(
        level=config.general.log_level,
        log_dir=config.general.log_dir,
    )
    _log.debug("mediavault-cli %s starting", __version__)


if __name__ == "__main__":  # pragma: no cover
    app()
