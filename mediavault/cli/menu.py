"""Interactive menu (FR-200–FR-202, FR-104, FR-1400, FR-1401)."""

from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console
from rich.table import Table

from mediavault.config.schema import Config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.models import RootType, ScanRoot, ScanStatus
from mediavault.reports.base import ReportScope
from mediavault.services.analyzer import (
    analyze_codecs,
    analyze_resolutions,
    analyze_subtitles,
)
from mediavault.services.library import (
    browse_episodes,
    browse_movies,
    browse_shows,
    search,
)
from mediavault.services.reporting import build_report_data, export_reports
from mediavault.services.scanner import scan_roots

console = Console()


def menu_loop(config: Config) -> None:
    """Main interactive menu loop."""
    conn = connect(config.general.db_path)
    migrate(conn)
    repo = Repository(conn)

    try:
        while True:
            _render_footer(repo)

            choices = [
                "1. Scan drives and update library",
                "2. Browse movies",
                "3. Browse TV shows and episodes",
                "4. Search and filter media",
                "5. Find duplicates",
                "6. Analyze codecs, resolutions, and subtitles",
                "7. Export reports",
                "0. Exit",
                "h. Help",
            ]

            choice = questionary.select(
                "What would you like to do?", choices=choices
            ).ask()

            if choice is None or choice.startswith("0"):
                console.print("[dim]Goodbye![/dim]")
                break

            if choice.startswith("h") or choice.startswith("?"):
                _print_help()
                continue

            if choice.startswith("1"):
                _option_scan(repo, config)
            elif choice.startswith("2"):
                _option_browse_movies(repo)
            elif choice.startswith("3"):
                _option_browse_episodes(repo)
            elif choice.startswith("4"):
                _option_search(repo)
            elif choice.startswith("5"):
                _option_duplicates(repo)
            elif choice.startswith("6"):
                _option_analyze(repo)
            elif choice.startswith("7"):
                _option_export(repo, config)

            console.print("")
    finally:
        conn.close()


def _print_help() -> None:
    console.print("\n[bold]MediaVault CLI Help[/bold]")
    console.print("1. Scan drives and update library: Scans your registered roots.")
    console.print("2. Browse movies: Lists all movies in the database.")
    console.print("3. Browse TV shows: Lists shows, then lets you drill in.")
    console.print("4. Search: Filter by title, year, codec, resolution, etc.")
    console.print("5. Duplicates: Shows exact and near-duplicate files.")
    console.print("6. Analyze: Codec, resolution, and subtitle coverage stats.")
    console.print("7. Export: Generate TXT, CSV, or Markdown reports.")
    console.print("0. Exit: Leave the application.")
    console.print("")


def _render_footer(repo: Repository) -> None:
    """Show the last scan stats (FR-1400, FR-1401)."""
    row = repo.conn.execute(
        "SELECT * FROM scans WHERE status IN ('completed', 'partial') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if row is None:
        console.print("\n[yellow]No scans yet — choose 1 to scan.[/yellow]")
        console.print("=" * 60)
        return

    ts = row["started_at"]
    status = row["status"]
    console.print(f"\n[bold]Last scan:[/bold] #{row['id']} at {ts} ({status})")

    m = row["movies_found"]
    s = row["shows_found"]
    e = row["episodes_found"]
    ed = row["exact_duplicates_found"]
    nd = row["near_duplicates_found"]

    console.print(
        f"Movies: {m}  Shows: {s}  Episodes: {e}  Exact dups: {ed}  Near dups: {nd}"
    )
    console.print("=" * 60)


# ---------------------------------------------------------------------------
# Option 1: Scan
# ---------------------------------------------------------------------------
def _option_scan(repo: Repository, config: Config) -> None:
    roots = repo.list_scan_roots()

    if not roots:
        console.print("\n[yellow]No roots registered.[/yellow]")
        prompt = "Enter a path to scan (or leave blank to cancel):"
        path_str = questionary.text(prompt).ask()
        if not path_str:
            return

        path = Path(path_str).expanduser().resolve()
        if not path.is_dir():
            console.print("[red]Invalid directory.[/red]")
            return

        root_type_str = questionary.select(
            "Select root type:", choices=["movies", "tv", "auto"]
        ).ask()

        root = ScanRoot(path=path, root_type=RootType(root_type_str))
        saved_root = repo.insert_scan_root(root)
        roots = [saved_root]
    else:
        action = questionary.select(
            "Scan options:",
            choices=[
                "Scan all registered roots",
                "Re-scan last roots",
                "Add a new root",
            ],
        ).ask()

        if action == "Add a new root":
            path_str = questionary.text("Enter a path to scan:").ask()
            if not path_str:
                return
            path = Path(path_str).expanduser().resolve()
            if not path.is_dir():
                console.print("[red]Invalid directory.[/red]")
                return
            root_type_str = questionary.select(
                "Select root type:", choices=["movies", "tv", "auto"]
            ).ask()
            root = ScanRoot(path=path, root_type=RootType(root_type_str))
            roots = [repo.insert_scan_root(root)]
        elif action == "Re-scan last roots":
            last_scan_id = repo.conn.execute(
                "SELECT MAX(id) FROM scans WHERE status IN ('completed', 'partial')"
            ).fetchone()[0]
            if not last_scan_id:
                console.print("[yellow]No prior successful scan found.[/yellow]")
                return
            rows = repo.conn.execute(
                "SELECT scan_root_id FROM scan_roots_scanned WHERE scan_id = ?",
                (last_scan_id,),
            ).fetchall()
            root_ids = [r[0] for r in rows]
            roots = [repo.get_scan_root(rid) for rid in root_ids]

    if not roots:
        return

    console.print(f"Scanning {len(roots)} root(s)...")
    try:
        result = scan_roots(repo, roots, config=config)
        if result.status == ScanStatus.COMPLETED:
            console.print("[green]Scan completed successfully.[/green]")
        else:
            status_val = result.status.value
            console.print(f"[yellow]Scan finished with status: {status_val}[/yellow]")

        m = result.movies_found
        s = result.shows_found
        e = result.episodes_found
        console.print(f"Movies: {m}, Shows: {s}, Episodes: {e}")
    except Exception as exc:
        console.print(f"[red]Scan failed: {exc}[/red]")


# ---------------------------------------------------------------------------
# Option 2: Browse Movies
# ---------------------------------------------------------------------------
def _option_browse_movies(repo: Repository) -> None:
    rows, total = browse_movies(repo)
    table = Table(title=f"Movies ({total})")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Resolution")
    table.add_column("Codec")
    table.add_column("Path")

    for m in rows:
        res = f"{m.width}x{m.height}" if m.width else ""
        table.add_row(
            m.parsed_title or "(untitled)",
            str(m.parsed_year or ""),
            res,
            m.codec or "",
            str(m.path),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Option 3: Browse TV Shows
# ---------------------------------------------------------------------------
def _option_browse_episodes(repo: Repository) -> None:
    shows, _ = browse_shows(repo)
    if not shows:
        console.print("[yellow]No shows found.[/yellow]")
        return

    show_choices = [f"{s.display_name} ({s.episode_count} eps)" for s in shows]
    show_choice = questionary.select("Select a show:", choices=show_choices).ask()
    if not show_choice:
        return

    idx = show_choices.index(show_choice)
    selected_show = shows[idx]

    rows = repo.conn.execute(
        "SELECT DISTINCT season FROM media_files "
        "WHERE show_key = ? AND season IS NOT NULL ORDER BY season",
        (selected_show.show_key,),
    ).fetchall()
    seasons = [r[0] for r in rows]

    season_choices = ["All seasons"] + [f"Season {s}" for s in seasons]
    prompt = "Select a season:"
    season_choice = questionary.select(prompt, choices=season_choices).ask()

    season_num = None
    if season_choice and season_choice != "All seasons":
        season_num = int(season_choice.split(" ")[1])

    episodes, total = browse_episodes(
        repo, show_key=selected_show.show_key, season=season_num
    )

    title = f"Episodes for {selected_show.display_name} ({total})"
    table = Table(title=title)
    table.add_column("Season")
    table.add_column("Episode")
    table.add_column("Resolution")
    table.add_column("Codec")
    table.add_column("Path")

    for e in episodes:
        res = f"{e.width}x{e.height}" if e.width else ""
        table.add_row(
            str(e.season or ""), str(e.episode or ""), res, e.codec or "", str(e.path)
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Option 4: Search
# ---------------------------------------------------------------------------
def _option_search(repo: Repository) -> None:
    title = questionary.text("Title contains (leave blank for all):").ask()
    if not title:
        title = None

    try:
        rows, total = search(repo, title=title)
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


# ---------------------------------------------------------------------------
# Option 5: Duplicates
# ---------------------------------------------------------------------------
def _option_duplicates(repo: Repository) -> None:
    console.print(
        "[yellow]Duplicate scanning is not yet fully wired into the menu.[/yellow]"
    )
    console.print("Use the `scan` command; duplicates are detected during scan.")


# ---------------------------------------------------------------------------
# Option 6: Analyze
# ---------------------------------------------------------------------------
def _option_analyze(repo: Repository) -> None:
    choice = questionary.select(
        "What to analyze?", choices=["Codecs", "Resolutions", "Subtitles"]
    ).ask()

    if choice == "Codecs":
        report = analyze_codecs(repo)
        table = Table(title=f"Codec Analysis (Total: {report.total_files})")
        table.add_column("Codec")
        table.add_column("Kind")
        table.add_column("Count")
        for row in report.rows:
            table.add_row(row.codec or "(unknown)", row.kind, str(row.count))
        console.print(table)
    elif choice == "Resolutions":
        report = analyze_resolutions(repo)
        title = f"Resolution Analysis (Total: {report.total_files})"
        table = Table(title=title)
        table.add_column("Resolution")
        table.add_column("Kind")
        table.add_column("Count")
        for row in report.rows:
            res = f"{row.width}x{row.height}" if row.width else "(unknown)"
            table.add_row(res, row.kind, str(row.count))
        console.print(table)
    elif choice == "Subtitles":
        report = analyze_subtitles(repo)
        console.print("[bold]Subtitle Coverage[/bold]")
        m_tot = report.movie_total
        m_both = report.movie_both
        m_ext = report.movie_external_only
        m_emb = report.movie_embedded_only
        m_nei = report.movie_neither
        console.print(
            f"Movies:   {m_tot} total, {m_both} both, "
            f"{m_ext} ext only, {m_emb} emb only, {m_nei} none"
        )

        e_tot = report.episode_total
        e_both = report.episode_both
        e_ext = report.episode_external_only
        e_emb = report.episode_embedded_only
        e_nei = report.episode_neither
        console.print(
            f"Episodes: {e_tot} total, {e_both} both, "
            f"{e_ext} ext only, {e_emb} emb only, {e_nei} none"
        )


# ---------------------------------------------------------------------------
# Option 7: Export
# ---------------------------------------------------------------------------
def _option_export(repo: Repository, config: Config) -> None:
    scope_str = questionary.select(
        "Select scope:", choices=["full", "movies", "show"]
    ).ask()
    if not scope_str:
        return
    scope = ReportScope(scope_str)

    show_key = None
    if scope == ReportScope.SHOW:
        shows, _ = browse_shows(repo)
        if not shows:
            console.print("[red]No shows found.[/red]")
            return
        choices = [s.display_name for s in shows]
        show_choice = questionary.select("Select a show:", choices=choices).ask()
        if not show_choice:
            return
        idx = choices.index(show_choice)
        show_key = shows[idx].show_key

    format_str = questionary.select(
        "Select format:", choices=["txt", "csv", "md"]
    ).ask()
    if not format_str:
        return

    try:
        data = build_report_data(repo, scope=scope, show_key=show_key)
        out_dir = Path(config.general.report_output_dir).expanduser()
        paths = export_reports(data, format=format_str, output_dir=out_dir)
        console.print(f"[green]Exported {len(paths)} file(s):[/green]")
        for p in paths:
            console.print(f"  {p}")
    except Exception as exc:
        console.print(f"[red]Export failed: {exc}[/red]")
