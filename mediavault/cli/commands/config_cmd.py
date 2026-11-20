"""Configuration subcommands (FR-1203–FR-1205)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mediavault.config import load_config
from mediavault.logging_setup import get_logger

console = Console()
_log = get_logger("cli.config")

# The default config template used by `config init` (FR-1204).
_DEFAULT_CONFIG_TEMPLATE = """\
[general]
db_path                  = "~/.local/share/mediavault-cli/mediavault.db"
log_dir                  = "~/.local/state/mediavault-cli/logs"
log_level                = "INFO"
ffprobe_path             = "ffprobe"
ffprobe_timeout_seconds  = 60
ffprobe_stderr_max_chars = 2000
subs_dir_name            = "subs"
report_output_dir        = "~/.local/share/mediavault-cli/reports"
probe_skip_unchanged     = true
follow_symlinks          = false
include_hidden           = false
skip_dirs                = [
    "@eaDir",
    "#recycle",
    ".Trash-*",
    "$RECYCLE.BIN",
    "System Volume Information",
]

[scan]
default_roots = []

[duplicates]
hash_chunk_bytes   = 1048576
partial_hash_bytes = 65536
"""


def show() -> None:
    """Show the resolved configuration and its source (FR-1203)."""
    try:
        config = load_config()
    except Exception as exc:
        console.print(f"[red]Error loading config: {exc}[/red]")
        raise typer.Exit(code=1)

    table = Table(title="Resolved Configuration")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    table.add_row("general.db_path", config.general.db_path, "resolved")
    table.add_row("general.log_dir", config.general.log_dir, "resolved")
    table.add_row("general.log_level", config.general.log_level, "resolved")
    table.add_row("general.ffprobe_path", config.general.ffprobe_path, "resolved")
    table.add_row(
        "general.ffprobe_timeout_seconds",
        str(config.general.ffprobe_timeout_seconds),
        "resolved",
    )
    table.add_row(
        "general.report_output_dir",
        config.general.report_output_dir,
        "resolved",
    )
    table.add_row(
        "duplicates.hash_chunk_bytes",
        str(config.duplicates.hash_chunk_bytes),
        "resolved",
    )
    table.add_row(
        "duplicates.partial_hash_bytes",
        str(config.duplicates.partial_hash_bytes),
        "resolved",
    )

    console.print(table)


def paths() -> None:
    """Print the resolved XDG, DB, log, and report directories (FR-1205)."""
    try:
        config = load_config()
    except Exception as exc:
        console.print(f"[red]Error loading config: {exc}[/red]")
        raise typer.Exit(code=1)

    xdg_config = Path("~/.config/mediavault-cli/config.toml").expanduser()
    project_config = Path("./config.toml").resolve()

    console.print("[bold]Configuration[/bold]")
    console.print(f"  XDG Config:     {xdg_config}")
    console.print(f"  Project Config: {project_config}")
    console.print("")
    console.print("[bold]Data[/bold]")
    console.print(f"  DB Path:        {Path(config.general.db_path).expanduser()}")
    console.print(f"  Log Dir:        {Path(config.general.log_dir).expanduser()}")
    console.print(
        f"  Report Dir:     {Path(config.general.report_output_dir).expanduser()}"
    )


def init(
    force: bool = typer.Option(False, "--force", help="Overwrite if exists"),
) -> None:
    """Write a default config.toml to the current directory (FR-1204)."""
    target = Path("./config.toml")
    if target.exists() and not force:
        console.print(
            f"[red]config.toml already exists at {target.resolve()}. "
            f"Use --force to overwrite.[/red]"
        )
        raise typer.Exit(code=1)

    target.write_text(_DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    console.print(f"[green]Created {target.resolve()}[/green]")
