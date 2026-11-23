"""Typer application entry point (FR-200–FR-209).

Phase 1 scope: --version and --help only. Subcommands are added in later
phases (§11). The app callback runs logging setup once, before any
command executes.
"""

from __future__ import annotations

import sys

import typer

from mediavault import __version__
from mediavault.cli.commands import analyze as cmd_analyze
from mediavault.cli.commands import browse as cmd_browse
from mediavault.cli.commands import config_cmd
from mediavault.cli.commands import export as cmd_export
from mediavault.cli.commands import scan as cmd_scan
from mediavault.cli.commands import search as cmd_search
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

    # If no subcommand was invoked, launch the interactive menu (FR-200).
    if len(sys.argv) == 1:
        from mediavault.cli.menu import menu_loop

        menu_loop(config)
        raise typer.Exit(code=0)


# --- Register subcommands ---
app.command(name="scan")(cmd_scan.scan)
app.command(name="search")(cmd_search.search)
app.command(name="export")(cmd_export.export)

browse_app = typer.Typer(help="Browse movies and episodes.")
browse_app.command("movies")(cmd_browse.movies)
browse_app.command("episodes")(cmd_browse.episodes)
app.add_typer(browse_app, name="browse")

analyze_app = typer.Typer(help="Analyze library statistics.")
analyze_app.command("codecs")(cmd_analyze.codecs)
app.add_typer(analyze_app, name="analyze")

config_app = typer.Typer(help="Manage configuration.")
config_app.command("show")(config_cmd.show)
config_app.command("paths")(config_cmd.paths)
config_app.command("init")(config_cmd.init)
app.add_typer(config_app, name="config")


if __name__ == "__main__":  # pragma: no cover
    app()
