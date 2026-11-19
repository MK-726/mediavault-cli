"""Analyzer tests (FR-1000–FR-1003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.services.analyzer import (
    analyze_codecs,
    analyze_resolutions,
    analyze_subtitles,
)


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    repo = Repository(conn)
    yield repo
    conn.close()


@pytest.fixture
def seeded(repo):
    """Mixed library: 3 movies, 3 episodes, varied codecs/resolutions/subs."""
    scan = repo.start_scan()

    def add(path: str, **kwargs) -> MediaFile:
        mf = MediaFile(
            path=Path(path),
            filename=Path(path).name,
            extension=Path(path).suffix.lower(),
            kind=kwargs.pop("kind", MediaKind.MOVIE),
            size=100,
            mtime_ns=1,
            parse_status=ParseStatus.OK,
            parse_confidence=ParseConfidence.HIGH,
            **kwargs,
        )
        return repo.insert_media_file(mf)

    a = add(
        "/lib/a.mkv",
        parsed_title="A",
        parsed_year=2020,
        codec="h264",
        width=1920,
        height=1080,
        has_embedded_subs=True,
    )
    add(
        "/lib/b.mkv",
        parsed_title="B",
        parsed_year=2021,
        codec="h264",
        width=1920,
        height=1080,
        has_embedded_subs=False,
    )
    add(
        "/lib/c.mkv",
        parsed_title="C",
        parsed_year=2022,
        codec="hevc",
        width=3840,
        height=2160,
        has_embedded_subs=False,
    )

    e1 = add(
        "/lib/S/Season-1/S.S01E01.mkv",
        kind=MediaKind.EPISODE,
        show_key="s",
        season=1,
        episode=1,
        parsed_title="S",
        codec="hevc",
        width=1920,
        height=1080,
        has_embedded_subs=True,
    )
    add(
        "/lib/S/Season-1/S.S01E02.mkv",
        kind=MediaKind.EPISODE,
        show_key="s",
        season=1,
        episode=2,
        parsed_title="S",
        codec="h264",
        width=1920,
        height=1080,
        has_embedded_subs=False,
    )
    add(
        "/lib/S/Season-2/S.S02E01.mkv",
        kind=MediaKind.EPISODE,
        show_key="s",
        season=2,
        episode=1,
        parsed_title="S",
        codec="h264",
        width=1280,
        height=720,
        has_embedded_subs=False,
    )

    # External subs: A (movie), e1 (episode)
    repo.conn.execute(
        (
            "INSERT INTO subtitles (media_file_id, path, kind, is_primary) "
            "VALUES (?, ?, 'external', 1)"
        ),
        (a.id, "/lib/a.srt"),
    )
    repo.conn.execute(
        (
            "INSERT INTO subtitles (media_file_id, path, kind, is_primary) "
            "VALUES (?, ?, 'external', 1)"
        ),
        (e1.id, "/lib/S/Season-1/S.S01E01.srt"),
    )
    repo.conn.commit()

    # Record scan membership so --scan tests work
    for mf in repo.conn.execute("SELECT id FROM media_files").fetchall():
        repo.record_scan_membership(scan.id, mf["id"])

    yield repo, scan
    # cleanup


# ---------------------------------------------------------------------------
# Codec analysis (FR-1000)
# ---------------------------------------------------------------------------
def test_analyze_codecs_by_kind(seeded):
    repo, _ = seeded
    result = analyze_codecs(repo)
    # Movies: 2 h264, 1 hevc
    # Episodes: 2 h264, 1 hevc
    by_codec = {(r.codec, r.kind): r.count for r in result.rows}
    assert by_codec[("h264", "movie")] == 2
    assert by_codec[("hevc", "movie")] == 1
    assert by_codec[("h264", "episode")] == 2
    assert by_codec[("hevc", "episode")] == 1
    assert result.total_files == 6


def test_analyze_codecs_handles_null_codec(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    repo = Repository(conn)

    repo.insert_media_file(
        MediaFile(
            path=Path("/lib/x.mkv"),
            filename="x.mkv",
            extension=".mkv",
            kind=MediaKind.MOVIE,
            size=1,
            mtime_ns=1,
            parse_status=ParseStatus.OK,
            codec=None,
        )
    )
    result = analyze_codecs(repo)
    null_rows = [r for r in result.rows if r.codec is None]
    assert len(null_rows) == 1
    assert null_rows[0].count == 1
    conn.close()


# ---------------------------------------------------------------------------
# Resolution analysis (FR-1000)
# ---------------------------------------------------------------------------
def test_analyze_resolutions_by_kind(seeded):
    repo, _ = seeded
    result = analyze_resolutions(repo)
    by_res = {(r.width, r.height, r.kind): r.count for r in result.rows}
    assert by_res[(1920, 1080, "movie")] == 2
    assert by_res[(3840, 2160, "movie")] == 1
    assert by_res[(1920, 1080, "episode")] == 2
    assert by_res[(1280, 720, "episode")] == 1


def test_analyze_resolutions_handles_null_dimensions(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    repo = Repository(conn)
    repo.insert_media_file(
        MediaFile(
            path=Path("/lib/x.mkv"),
            filename="x.mkv",
            extension=".mkv",
            kind=MediaKind.MOVIE,
            size=1,
            mtime_ns=1,
            parse_status=ParseStatus.OK,
            width=None,
            height=None,
        )
    )
    result = analyze_resolutions(repo)
    null_rows = [r for r in result.rows if r.width is None]
    assert len(null_rows) == 1
    conn.close()


# ---------------------------------------------------------------------------
# Subtitle analysis (FR-1000)
# ---------------------------------------------------------------------------
def test_analyze_subtitles_coverage(seeded):
    repo, _ = seeded
    result = analyze_subtitles(repo)
    # Movies: A (both), B (neither), C (neither)
    # Episodes: S01E01 (both), S01E02 (neither), S02E01 (neither)
    assert result.movie_total == 3
    assert result.movie_both == 1
    assert result.movie_neither == 2
    assert result.movie_external_only == 0
    assert result.movie_embedded_only == 0

    assert result.episode_total == 3
    assert result.episode_both == 1
    assert result.episode_neither == 2
    assert result.episode_external_only == 0
    assert result.episode_embedded_only == 0


# ---------------------------------------------------------------------------
# --scan N scope (FR-1002)
# ---------------------------------------------------------------------------
def test_analyze_codecs_scan_scope(seeded):
    repo, scan1 = seeded
    # Add a second scan and a file that belongs only to it
    scan2 = repo.start_scan()
    new_mf = repo.insert_media_file(
        MediaFile(
            path=Path("/lib/new.mkv"),
            filename="new.mkv",
            extension=".mkv",
            kind=MediaKind.MOVIE,
            size=1,
            mtime_ns=1,
            parse_status=ParseStatus.OK,
            codec="av1",
        )
    )
    repo.record_scan_membership(scan2.id, new_mf.id)

    # Unscoped: 7 files
    result_all = analyze_codecs(repo)
    assert result_all.total_files == 7

    # Scoped to scan1: 6 files, no av1
    result_s1 = analyze_codecs(repo, scan_id=scan1.id)
    assert result_s1.total_files == 6
    assert not any(r.codec == "av1" for r in result_s1.rows)

    # Scoped to scan2: 1 file, only av1
    result_s2 = analyze_codecs(repo, scan_id=scan2.id)
    assert result_s2.total_files == 1
    assert result_s2.rows[0].codec == "av1"
