from pathlib import Path

import typer
from rich.console import Console

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.reports.base import ReportScope
from mediavault.services.reporting import build_report_data, export_reports

console = Console()


def export(
    format: str = typer.Option("txt", "--format", "-f", help="txt, csv, or md"),
    scope: str = typer.Option("full", "--scope", "-s", help="full, movies, or show"),
    show: str = typer.Option(None, "--show", help="Show key (required for scope=show)"),
):
    """Export reports."""
    config = load_config()
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    try:
        report_scope = ReportScope(scope.lower())
    except ValueError:
        console.print(f"[red]Invalid scope: {scope}[/red]")
        raise typer.Exit(code=2)

    try:
        data = build_report_data(repo, scope=report_scope, show_key=show)
        out_dir = Path(config.general.report_output_dir).expanduser()

        paths = export_reports(data, format=format, output_dir=out_dir)

        console.print(f"[green]Exported {len(paths)} file(s):[/green]")
        for p in paths:
            console.print(f"  {p}")
    except UsageError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=2)
    finally:
        conn.close()
