import typer
from rich.console import Console
from rich.table import Table

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.services.library import browse_episodes, browse_movies

console = Console()


def movies(include_missing: bool = typer.Option(False, "--include-missing")):
    """Browse movies."""
    config = load_config()
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    rows, total = browse_movies(repo, include_missing=include_missing)

    table = Table(title=f"Movies ({total})")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Resolution")
    table.add_column("Codec")
    table.add_column("Path")

    for m in rows:
        table.add_row(
            m.parsed_title or "(untitled)",
            str(m.parsed_year or ""),
            f"{m.width}x{m.height}" if m.width else "",
            m.codec or "",
            str(m.path),
        )
    console.print(table)
    conn.close()


def episodes(
    show: str = typer.Option(..., "--show", help="Show key"),
    season: int = typer.Option(None, "--season", help="Season number"),
    include_missing: bool = typer.Option(False, "--include-missing"),
):
    """Browse episodes for a show."""
    config = load_config()
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    rows, total = browse_episodes(
        repo, show_key=show, season=season, include_missing=include_missing
    )

    table = Table(title=f"Episodes for {show} ({total})")
    table.add_column("Season")
    table.add_column("Episode")
    table.add_column("Title")
    table.add_column("Resolution")
    table.add_column("Path")

    for e in rows:
        table.add_row(
            str(e.season or ""),
            str(e.episode or ""),
            e.parsed_title or "",
            f"{e.width}x{e.height}" if e.width else "",
            str(e.path),
        )
    console.print(table)
    conn.close()


# Note: in the real `main.py`, we'll add a Typer sub-app for browse to dispatch
# between movies and episodes. For this step, we just need the functions.
