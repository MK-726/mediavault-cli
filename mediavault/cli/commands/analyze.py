import typer
from rich.console import Console
from rich.table import Table

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.services.analyzer import (
    analyze_codecs,
)

console = Console()


def codecs(scan_id: int = typer.Option(None, "--scan")):
    """Analyze codec distribution."""
    config = load_config()
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    report = analyze_codecs(repo, scan_id=scan_id)

    table = Table(title=f"Codec Analysis (Total: {report.total_files})")
    table.add_column("Codec")
    table.add_column("Kind")
    table.add_column("Count")

    for row in report.rows:
        table.add_row(row.codec or "(unknown)", row.kind, str(row.count))

    console.print(table)
    conn.close()
