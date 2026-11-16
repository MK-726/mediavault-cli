"""Scan orchestration tests (FR-102, FR-102a, FR-103, FR-806, FR-807)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.models import (
    MediaKind,
    ParseStatus,
    RootType,
    ScanRoot,
    ScanStatus,
)
from mediavault.services.scanner import scan_roots


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def cfg(tmp_path):
    import os

    for k in list(os.environ):
        if k.startswith("MEDIAVAULT_CLI_"):
            os.environ.pop(k, None)
    return load_config(project_config=None)


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield Repository(conn)
    conn.close()


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------
def test_scan_movies_root_persists_files(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    _touch(movies / "A.Movie.2020.mkv")
    _touch(movies / "Another.Movie.2021.mp4")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan = scan_roots(repo, [root], config=cfg)

    assert scan.status == ScanStatus.COMPLETED
    assert scan.movies_found == 2
    assert scan.episodes_found == 0
    assert scan.shows_found == 0

    # Persisted files
    a = repo.get_media_file_by_path(movies / "A.Movie.2020.mkv")
    assert a is not None
    assert a.kind == MediaKind.MOVIE
    assert a.parse_status == ParseStatus.OK
    assert a.parsed_title == "A Movie"
    assert a.parsed_year == 2020
    assert a.last_seen_scan_id == scan.id

    # Scan membership recorded (FR-102a)
    members = repo.list_scan_members(scan.id)
    assert {m.path.name for m in members} == {
        "A.Movie.2020.mkv",
        "Another.Movie.2021.mp4",
    }


def test_scan_tv_root_persists_episodes(tmp_path, repo, cfg):
    tv = tmp_path / "tv"
    _touch(tv / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E01.mkv")
    _touch(tv / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E02.mkv")
    _touch(tv / "Breaking-Bad" / "Season-2" / "Breaking.Bad.S02E01.mkv")

    root = repo.insert_scan_root(ScanRoot(path=tv, root_type=RootType.TV))
    scan = scan_roots(repo, [root], config=cfg)

    assert scan.status == ScanStatus.COMPLETED
    assert scan.episodes_found == 3
    assert scan.shows_found == 1

    members = repo.list_scan_members(scan.id)
    assert len(members) == 3
    for m in members:
        assert m.kind == MediaKind.EPISODE
        assert m.show_key == "breaking_bad"
        assert m.season is not None
        assert m.episode is not None


# ---------------------------------------------------------------------------
# FR-806: missing files marked, not deleted
# ---------------------------------------------------------------------------
def test_second_scan_marks_removed_files_missing(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    _touch(movies / "A.mkv")
    _touch(movies / "B.mkv")
    _touch(movies / "C.mkv")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan1 = scan_roots(repo, [root], config=cfg)
    assert scan1.movies_found == 3

    # Remove B, add D
    (movies / "B.mkv").unlink()
    _touch(movies / "D.mkv")

    scan2 = scan_roots(repo, [root], config=cfg)
    assert scan2.movies_found == 3
    assert scan2.id != scan1.id

    b = repo.get_media_file_by_path(movies / "B.mkv")
    assert b is not None
    assert b.missing_since_scan_id == scan2.id
    assert b.last_seen_scan_id == scan1.id  # not updated

    d = repo.get_media_file_by_path(movies / "D.mkv")
    assert d is not None
    assert d.missing_since_scan_id is None
    assert d.last_seen_scan_id == scan2.id


# ---------------------------------------------------------------------------
# FR-807: returning file clears missing_since_scan_id
# ---------------------------------------------------------------------------
def test_returning_file_clears_missing(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    _touch(movies / "A.mkv")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan_roots(repo, [root], config=cfg)

    (movies / "A.mkv").unlink()
    scan2 = scan_roots(repo, [root], config=cfg)
    a = repo.get_media_file_by_path(movies / "A.mkv")
    assert a.missing_since_scan_id == scan2.id

    _touch(movies / "A.mkv")
    scan3 = scan_roots(repo, [root], config=cfg)
    a = repo.get_media_file_by_path(movies / "A.mkv")
    assert a.missing_since_scan_id is None
    assert a.last_seen_scan_id == scan3.id


# ---------------------------------------------------------------------------
# FR-322: unmounted root → partial, files NOT marked missing
# ---------------------------------------------------------------------------
def test_missing_root_marks_scan_partial_and_skips_missing_marking(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    _touch(movies / "A.mkv")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan1 = scan_roots(repo, [root], config=cfg)
    assert scan1.movies_found == 1

    # Simulate the drive being unmounted (the directory is gone).
    (movies / "A.mkv").unlink()
    movies.rmdir()

    scan2 = scan_roots(repo, [root], config=cfg)
    assert scan2.status == ScanStatus.PARTIAL
    assert scan2.filesystem_errors >= 1

    a = repo.get_media_file_by_path(movies / "A.mkv")
    assert a is not None
    # FR-322: file was NOT marked missing because its root was unmounted.
    assert a.missing_since_scan_id is None


# ---------------------------------------------------------------------------
# Last successful scan (FR-103)
# ---------------------------------------------------------------------------
def test_last_successful_scan_recorded(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    _touch(movies / "A.mkv")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan = scan_roots(repo, [root], config=cfg)

    # The scanner should have recorded last_successful_scan_id in meta.
    row = repo.conn.execute(
        "SELECT value FROM meta WHERE key = 'last_successful_scan_id'"
    ).fetchone()
    assert row is not None
    assert int(row[0]) == scan.id
