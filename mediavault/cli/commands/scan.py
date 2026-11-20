import typer
from rich.console import Console

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import MediaVaultError
from mediavault.models import RootType, ScanRoot, ScanStatus
from mediavault.paths import validate_directory
from mediavault.services.scanner import scan_roots

console = Console()


def scan(
    root: list[str] = typer.Option(None, "--root", help="Directories to scan"),
    last: bool = typer.Option(False, "--last", help="Re-scan last roots"),
):
    """Scan drives and update the library."""
    config = load_config()

    if root and last:
        console.print("[red]Error: --root and --last are mutually exclusive.[/red]")
        raise typer.Exit(code=2)

    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    roots_to_scan = []

    if last:
        # Find roots from the last scan
        last_scan_id = repo.conn.execute(
            "SELECT MAX(id) FROM scans WHERE status IN ('completed', 'partial')"
        ).fetchone()[0]
        if not last_scan_id:
            console.print("[yellow]No prior successful scan found.[/yellow]")
            raise typer.Exit(code=0)

        rows = repo.conn.execute(
            "SELECT scan_root_id FROM scan_roots_scanned WHERE scan_id = ?",
            (last_scan_id,),
        ).fetchall()
        root_ids = [r[0] for r in rows]
        roots_to_scan = [repo.get_scan_root(rid) for rid in root_ids]
    elif root:
        for r in root:
            try:
                path = validate_directory(r)
                # For this command, we'll assume auto root type if not specified.
                # In the full CLI, we would ask for root_type.
                roots_to_scan.append(ScanRoot(path=path, root_type=RootType.AUTO))
            except Exception as exc:
                console.print(f"[red]Invalid path {r}: {exc}[/red]")
                raise typer.Exit(code=2)
    else:
        roots_to_scan = repo.list_scan_roots()
        if not roots_to_scan:
            console.print(
                "[red]No registered roots. Use --root to scan a directory.[/red]"
            )
            raise typer.Exit(code=2)

    try:
        result = scan_roots(repo, roots_to_scan, config=config)
        if result.status == ScanStatus.COMPLETED:
            console.print("[green]Scan completed successfully.[/green]")
        else:
            console.print(
                f"[yellow]Scan finished with status: {result.status.value}[/yellow]"
            )

        console.print(f"Movies: {result.movies_found}")
        console.print(f"Shows: {result.shows_found}")
        console.print(f"Episodes: {result.episodes_found}")

        if result.status == ScanStatus.PARTIAL:
            raise typer.Exit(code=3)
    except MediaVaultError as exc:
        console.print(f"[red]Scan failed: {exc}[/red]")
        raise typer.Exit(code=1)
    finally:
        conn.close()
