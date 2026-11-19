"""Library browse and search service (FR-900–FR-905)."""

from __future__ import annotations

from typing import Any

from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.logging_setup import get_logger
from mediavault.models import MediaFile, MediaKind, ShowSummary

_log = get_logger("services.library")


def _query_media(
    repo: Repository,
    *,
    kind: MediaKind | None = None,
    title: str | None = None,
    year: int | None = None,
    codec: str | None = None,
    resolution: str | None = None,
    min_duration: float | None = None,
    max_duration: float | None = None,
    show_key: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    has_subs: bool | None = None,
    has_external_subs: bool | None = None,
    has_embedded_subs: bool | None = None,
    include_missing: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[MediaFile], int]:
    """Internal helper: build and execute a media_files query."""
    where_clauses = []
    params: list[Any] = []

    # Base filters
    if kind is not None:
        where_clauses.append("m.kind = ?")
        params.append(kind.value)

    if title is not None:
        # Case-insensitive partial match on parsed_title
        where_clauses.append("LOWER(m.parsed_title) LIKE LOWER(?)")
        params.append(f"%{title}%")

    if year is not None:
        where_clauses.append("m.parsed_year = ?")
        params.append(year)

    if codec is not None:
        where_clauses.append("LOWER(m.codec) = LOWER(?)")
        params.append(codec)

    if resolution is not None:
        # resolution is passed as "WIDTHxHEIGHT"
        try:
            w_str, h_str = resolution.lower().split("x")
            where_clauses.append("m.width = ? AND m.height = ?")
            params.extend([int(w_str), int(h_str)])
        except ValueError:
            raise UsageError(
                f"Invalid resolution format '{resolution}'. Use WxH (e.g. 1920x1080)."
            )

    if min_duration is not None:
        where_clauses.append("m.duration >= ?")
        params.append(min_duration)

    if max_duration is not None:
        where_clauses.append("m.duration <= ?")
        params.append(max_duration)

    # Episode-specific filters
    if show_key is not None:
        where_clauses.append("m.show_key = ?")
        params.append(show_key)

    if season is not None:
        where_clauses.append("m.season = ?")
        params.append(season)

    if episode is not None:
        where_clauses.append("m.episode = ?")
        params.append(episode)

    # Subtitle filters (FR-903)
    if (
        has_subs is not None
        or has_external_subs is not None
        or has_embedded_subs is not None
    ):
        # We need to join the subtitles table to check for external subs
        pass  # We will handle this by building a subquery in the WHERE clause

    if has_external_subs:
        where_clauses.append(
            (
                "EXISTS (SELECT 1 FROM subtitles s "
                "WHERE s.media_file_id = m.id AND s.kind = 'external')"
            )
        )
    if has_embedded_subs:
        where_clauses.append("m.has_embedded_subs = 1")

    if has_subs:
        # OR condition: has external OR has embedded
        where_clauses.append(
            (
                "(m.has_embedded_subs = 1 OR EXISTS "
                "(SELECT 1 FROM subtitles s "
                "WHERE s.media_file_id = m.id AND s.kind = 'external'))"
            )
        )
    elif has_subs is False:  # This is the --no-subs case
        where_clauses.append(
            (
                "(m.has_embedded_subs = 0 AND NOT EXISTS "
                "(SELECT 1 FROM subtitles s "
                "WHERE s.media_file_id = m.id AND s.kind = 'external'))"
            )
        )

    # Missing files (FR-904)
    if not include_missing:
        where_clauses.append("m.missing_since_scan_id IS NULL")

    # Build the base SQL
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Count total (for pagination)
    count_sql = f"SELECT COUNT(*) FROM media_files m {where_sql}"
    total = repo.conn.execute(count_sql, params).fetchone()[0]

    # Fetch paginated rows
    query_sql = f"SELECT m.* FROM media_files m {where_sql} ORDER BY m.id"

    if limit is not None:
        query_sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    rows = repo.conn.execute(query_sql, params).fetchall()
    media_files = [repo._row_to_media_file(row) for row in rows]

    return media_files, total


# ---------------------------------------------------------------------------
# Public API (FR-900–FR-902)
# ---------------------------------------------------------------------------
def browse_movies(
    repo: Repository,
    *,
    include_missing: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[MediaFile], int]:
    """Browse movies (FR-900)."""
    return _query_media(
        repo,
        kind=MediaKind.MOVIE,
        include_missing=include_missing,
        limit=limit,
        offset=offset,
    )


def browse_shows(repo: Repository) -> tuple[list[ShowSummary], int]:
    """Browse TV shows with episode/season counts (FR-901)."""
    # We group by show_key to get distinct shows and count episodes/seasons.
    # Only count episodes where missing_since_scan_id is NULL.
    sql = """
        SELECT
            show_key,
            MAX(parsed_title) as display_name,
            COUNT(id) as episode_count,
            COUNT(DISTINCT season) as season_count
        FROM media_files
        WHERE kind = 'episode'
          AND missing_since_scan_id IS NULL
          AND show_key IS NOT NULL
        GROUP BY show_key
        ORDER BY show_key
    """
    rows = repo.conn.execute(sql).fetchall()
    shows = [
        ShowSummary(
            show_key=row["show_key"],
            display_name=row["display_name"] or row["show_key"],
            episode_count=row["episode_count"],
            season_count=row["season_count"],
        )
        for row in rows
    ]
    return shows, len(shows)


def browse_episodes(
    repo: Repository,
    *,
    show_key: str,
    season: int | None = None,
    include_missing: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[MediaFile], int]:
    """Browse episodes for a specific show (FR-902)."""
    return _query_media(
        repo,
        kind=MediaKind.EPISODE,
        show_key=show_key,
        season=season,
        include_missing=include_missing,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Search (FR-903)
# ---------------------------------------------------------------------------
def search(
    repo: Repository,
    *,
    title: str | None = None,
    year: int | None = None,
    codec: str | None = None,
    resolution: str | None = None,
    min_duration: float | None = None,
    max_duration: float | None = None,
    show_key: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    has_subs: bool | None = None,
    has_external_subs: bool | None = None,
    has_embedded_subs: bool | None = None,
    no_subs: bool = False,
    include_missing: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[MediaFile], int]:
    """Multi-filter search (FR-903, FR-903a)."""

    # FR-903a: Conflicting filter validation
    if no_subs:
        if has_subs or has_external_subs or has_embedded_subs:
            raise UsageError(
                (
                    "Conflicting subtitle filters: --no-subs "
                    "cannot be combined with other subtitle filters."
                )
            )
        has_subs = False  # No-subs is the inverse of has-subs

    return _query_media(
        repo,
        title=title,
        year=year,
        codec=codec,
        resolution=resolution,
        min_duration=min_duration,
        max_duration=max_duration,
        show_key=show_key,
        season=season,
        episode=episode,
        has_subs=has_subs,
        has_external_subs=has_external_subs,
        has_embedded_subs=has_embedded_subs,
        include_missing=include_missing,
        limit=limit,
        offset=offset,
    )
