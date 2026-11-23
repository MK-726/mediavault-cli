import typer
from rich.console import Console
from rich.table import Table

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.services.library import search as svc_search

console = Console()


def search(
    title: str = typer.Option(None, "--title"),
    year: int = typer.Option(None, "--year"),
    codec: str = typer.Option(None, "--codec"),
    resolution: str = typer.Option(None, "--resolution"),
    min_duration: float = typer.Option(None, "--min-duration"),
    max_duration: float = typer.Option(None, "--max-duration"),
    has_subs: bool = typer.Option(False, "--has-subs"),
    has_external_subs: bool = typer.Option(False, "--has-external-subs"),
    has_embedded_subs: bool = typer.Option(False, "--has-embedded-subs"),
    no_subs: bool = typer.Option(False, "--no-subs"),
    include_missing: bool = typer.Option(False, "--include-missing"),
):
    """Search and filter media."""
    config = load_config()
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    try:
        rows, total = svc_search(
            repo,
            title=title,
            year=year,
            codec=codec,
            resolution=resolution,
            min_duration=min_duration,
            max_duration=max_duration,
            has_subs=has_subs,
            has_external_subs=has_external_subs,
            has_embedded_subs=has_embedded_subs,
            no_subs=no_subs,
            include_missing=include_missing,
        )
        table = Table(title=f"Search Results ({total})")
        table.add_column("Title / Show")
        table.add_column("Type")
        table.add_column("Path")

        for m in rows:
            title_str = m.parsed_title or m.show_key or ""
            table.add_row(title_str, m.kind.value, str(m.path))

        console.print(table)
    except UsageError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=2)
    finally:
        conn.close()
