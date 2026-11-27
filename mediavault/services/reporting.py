"""Report runner service (FR-1101, FR-1105, FR-1109, FR-1110)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.logging_setup import get_logger
from mediavault.models import MediaFile, MediaKind, ParseStatus
from mediavault.reports.base import ReportData, ReportScope
from mediavault.reports.csv_report import CsvReport
from mediavault.reports.markdown import MarkdownReport
from mediavault.reports.txt import TxtReport
from mediavault.services.library import browse_episodes, browse_movies

_log = get_logger("services.reporting")


def build_report_data(
    repo: Repository,
    *,
    scope: ReportScope,
    show_key: str | None = None,
) -> ReportData:
    """Query the DB and construct a ReportData object for formatting."""
    if scope == ReportScope.SHOW and not show_key:
        raise UsageError("--scope show requires --show NAME")

    movies: list[MediaFile] = []
    episodes: list[MediaFile] = []

    if scope in (ReportScope.FULL, ReportScope.MOVIES):
        movies, _ = browse_movies(repo, include_missing=False)

    if scope in (ReportScope.FULL, ReportScope.SHOW):
        if show_key:
            episodes, _ = browse_episodes(
                repo, show_key=show_key, include_missing=False
            )
        else:
            # For FULL, we need all episodes, not just one show.
            # We can use _query_media directly for this.
            from mediavault.services.library import _query_media

            episodes, _ = _query_media(
                repo, kind=MediaKind.EPISODE, include_missing=False
            )

    # Query all data for the problems section and external subs.
    # We fetch ALL files (including missing) for the problem report.
    all_files_rows = repo.conn.execute("SELECT * FROM media_files").fetchall()
    all_files = [repo._row_to_media_file(r) for r in all_files_rows]

    # Files with external subs
    ext_sub_rows = repo.conn.execute(
        "SELECT DISTINCT media_file_id FROM subtitles WHERE kind = 'external'"
    ).fetchall()
    files_with_ext = frozenset(row[0] for row in ext_sub_rows)

    # Problem lists (FR-1104)
    orphan_sub_rows = repo.conn.execute(
        "SELECT path FROM subtitles WHERE kind = 'external' AND media_file_id IS NULL"
    ).fetchall()
    orphan_subtitles = tuple(Path(row[0]) for row in orphan_sub_rows)

    unparsed = tuple(f for f in all_files if f.parse_status == ParseStatus.UNPARSED)
    missing = tuple(f for f in all_files if f.missing_since_scan_id is not None)

    # Probe errors are files that exist but have no codec and weren't probed.
    # (This is a heuristic; a more precise way would be to track failed probes.)
    probe_errors = tuple(
        f for f in all_files if f.probed_at is None and f.missing_since_scan_id is None
    )

    # Movies missing external subs (only relevant for movies scope)
    movies_without_ext = tuple(
        m
        for m in all_files
        if m.kind == MediaKind.MOVIE
        and m.id not in files_with_ext
        and m.missing_since_scan_id is None
    )

    return ReportData(
        scope=scope,
        generated_at=datetime.now(timezone.utc).isoformat(),
        movies=tuple(movies),
        episodes=tuple(episodes),
        files_with_external_subs=files_with_ext,
        orphan_subtitles=orphan_subtitles,
        movies_without_external_subs=movies_without_ext,
        unparsed_files=unparsed,
        probe_error_files=probe_errors,
        missing_files=missing,
    )


def export_reports(
    data: ReportData,
    *,
    format: str,
    output_dir: Path,
) -> list[Path]:
    """Export the ReportData to files in *output_dir* (FR-1105)."""
    # FR-1110: Reject if output_dir is inside a scan root.
    # (In a full CLI, we'd pass the scan_roots here. For now, we assume
    # the CLI has already checked this, but we'll add the check in Step 2).

    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{data.scope.value}-{timestamp}"

    format = format.lower()
    if format == "txt":
        path = output_dir / f"{base_name}.txt"
        TxtReport().write(data, path)
        return [path]
    elif format == "csv":
        base_path = output_dir / base_name
        return CsvReport().write(data, base_path)
    elif format == "md":
        path = output_dir / f"{base_name}.md"
        MarkdownReport().write(data, path)
        return [path]
    else:
        raise UsageError(f"Unknown format: {format}")
