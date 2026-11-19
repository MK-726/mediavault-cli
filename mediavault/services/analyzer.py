"""Read-only analysis service (FR-1000–FR-1003)."""

from __future__ import annotations

from mediavault.database.repository import Repository
from mediavault.logging_setup import get_logger
from mediavault.models import (
    CodecReport,
    CodecRow,
    ResolutionReport,
    ResolutionRow,
    SubtitleReport,
)

_log = get_logger("services.analyzer")


def _scan_filter(scan_id: int | None, table_alias: str = "m") -> tuple[str, list]:
    """Return a WHERE clause fragment and params for the scan filter."""
    if scan_id is None:
        return "", []
    # FR-1002: restrict to files that were members of the given scan.
    fragment = (
        f" AND EXISTS (SELECT 1 FROM scan_media_files smf "
        f"WHERE smf.media_file_id = {table_alias}.id AND smf.scan_id = ?)"
    )
    return fragment, [scan_id]


# ---------------------------------------------------------------------------
# Codec analysis (FR-1000)
# ---------------------------------------------------------------------------
def analyze_codecs(repo: Repository, *, scan_id: int | None = None) -> CodecReport:
    """Return counts per (codec, kind)."""
    filter_sql, filter_params = _scan_filter(scan_id)

    sql = f"""
        SELECT codec, kind, COUNT(*) as count
        FROM media_files m
        WHERE missing_since_scan_id IS NULL
        {filter_sql}
        GROUP BY codec, kind
        ORDER BY count DESC, codec, kind
    """
    rows = repo.conn.execute(sql, filter_params).fetchall()

    codec_rows = tuple(
        CodecRow(
            codec=row["codec"],
            kind=row["kind"],
            count=row["count"],
        )
        for row in rows
    )

    total = sum(r.count for r in codec_rows)
    return CodecReport(rows=codec_rows, total_files=total)


# ---------------------------------------------------------------------------
# Resolution analysis (FR-1000)
# ---------------------------------------------------------------------------
def analyze_resolutions(
    repo: Repository, *, scan_id: int | None = None
) -> ResolutionReport:
    """Return counts per (width, height, kind)."""
    filter_sql, filter_params = _scan_filter(scan_id)

    sql = f"""
        SELECT width, height, kind, COUNT(*) as count
        FROM media_files m
        WHERE missing_since_scan_id IS NULL
        {filter_sql}
        GROUP BY width, height, kind
        ORDER BY width DESC, height DESC, kind
    """
    rows = repo.conn.execute(sql, filter_params).fetchall()

    resolution_rows = tuple(
        ResolutionRow(
            width=row["width"],
            height=row["height"],
            kind=row["kind"],
            count=row["count"],
        )
        for row in rows
    )

    total = sum(r.count for r in resolution_rows)
    return ResolutionReport(rows=resolution_rows, total_files=total)


# ---------------------------------------------------------------------------
# Subtitle analysis (FR-1000)
# ---------------------------------------------------------------------------
def analyze_subtitles(
    repo: Repository, *, scan_id: int | None = None
) -> SubtitleReport:
    """Return subtitle coverage split by movie vs. episode."""
    filter_sql, filter_params = _scan_filter(scan_id)

    # For each file we compute two flags:
    #   has_ext = EXISTS any external subtitle
    #   has_emb = has_embedded_subs == 1
    # Then we bucket into (both, ext_only, emb_only, neither) by kind.
    #
    # `has_embedded_subs` may be NULL (unknown, missing FFprobe). Treat
    # NULL as False for analysis purposes — it's not "has subs".
    sql = f"""
        WITH flags AS (
            SELECT
                m.kind,
                m.has_embedded_subs,
                EXISTS (
                    SELECT 1 FROM subtitles s
                    WHERE s.media_file_id = m.id
                      AND s.kind = 'external'
                ) as has_ext
            FROM media_files m
            WHERE missing_since_scan_id IS NULL
            {filter_sql}
        )
        SELECT
            kind,
            SUM(
                CASE WHEN has_ext
                     AND COALESCE(has_embedded_subs, 0) = 1
                THEN 1 ELSE 0 END
            ) AS both_count,
            SUM(
                CASE WHEN has_ext
                     AND COALESCE(has_embedded_subs, 0) = 0
                THEN 1 ELSE 0 END
            ) AS ext_only_count,
            SUM(
                CASE WHEN NOT has_ext
                     AND COALESCE(has_embedded_subs, 0) = 1
                THEN 1 ELSE 0 END
            ) AS emb_only_count,
            SUM(
                CASE WHEN NOT has_ext
                     AND COALESCE(has_embedded_subs, 0) = 0
                THEN 1 ELSE 0 END
            ) AS neither_count,
            COUNT(*) AS total
        FROM flags
        GROUP BY kind
    """
    rows = repo.conn.execute(sql, filter_params).fetchall()

    by_kind = {row["kind"]: row for row in rows}
    movie = by_kind.get("movie")
    episode = by_kind.get("episode")

    def _val(row, key: str) -> int:
        return int(row[key]) if row is not None else 0

    return SubtitleReport(
        movie_total=_val(movie, "total"),
        movie_both=_val(movie, "both_count"),
        movie_external_only=_val(movie, "ext_only_count"),
        movie_embedded_only=_val(movie, "emb_only_count"),
        movie_neither=_val(movie, "neither_count"),
        episode_total=_val(episode, "total"),
        episode_both=_val(episode, "both_count"),
        episode_external_only=_val(episode, "ext_only_count"),
        episode_embedded_only=_val(episode, "emb_only_count"),
        episode_neither=_val(episode, "neither_count"),
    )
