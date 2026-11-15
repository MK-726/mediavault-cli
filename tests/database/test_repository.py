"""Repository tests (FR-804)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseStatus,
    RootType,
    ScanRoot,
    ScanStatus,
)


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield Repository(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Scan roots
# ---------------------------------------------------------------------------
def test_insert_and_get_scan_root(repo, tmp_path):
    root = ScanRoot(path=tmp_path / "movies", root_type=RootType.MOVIES)
    saved = repo.insert_scan_root(root)
    assert saved.id is not None
    fetched = repo.get_scan_root(saved.id)
    assert fetched.path == root.path
    assert fetched.root_type == RootType.MOVIES


def test_list_scan_roots(repo, tmp_path):
    repo.insert_scan_root(ScanRoot(path=tmp_path / "a", root_type=RootType.MOVIES))
    repo.insert_scan_root(ScanRoot(path=tmp_path / "b", root_type=RootType.TV))
    assert len(repo.list_scan_roots()) == 2


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------
def test_start_and_finish_scan(repo):
    scan = repo.start_scan()
    assert scan.id is not None
    assert scan.status == ScanStatus.RUNNING

    finished = repo.finish_scan(
        scan.id,
        status=ScanStatus.COMPLETED,
        movies_found=3,
        shows_found=1,
        episodes_found=4,
    )
    assert finished.status == ScanStatus.COMPLETED
    assert finished.movies_found == 3


# ---------------------------------------------------------------------------
# Media files
# ---------------------------------------------------------------------------
def _mf(path: Path, kind: MediaKind = MediaKind.MOVIE) -> MediaFile:
    return MediaFile(
        path=path,
        filename=path.name,
        extension=path.suffix.lower(),
        kind=kind,
        size=10,
        mtime_ns=20,
        parse_status=ParseStatus.UNPARSED,
    )


def test_insert_and_get_media_file(repo, tmp_path):
    mf = _mf(tmp_path / "a.mkv")
    saved = repo.insert_media_file(mf)
    assert saved.id is not None
    got = repo.get_media_file(saved.id)
    assert got.path == mf.path
    assert got.kind == MediaKind.MOVIE


def test_get_media_file_by_path(repo, tmp_path):
    mf = _mf(tmp_path / "a.mkv")
    repo.insert_media_file(mf)
    got = repo.get_media_file_by_path(tmp_path / "a.mkv")
    assert got is not None
    assert got.id is not None


def test_update_media_file(repo, tmp_path):
    mf = repo.insert_media_file(_mf(tmp_path / "a.mkv"))
    mf.parsed_title = "A Movie"
    mf.parsed_year = 2020
    mf.parse_status = ParseStatus.OK
    repo.update_media_file(mf)
    got = repo.get_media_file(mf.id)
    assert got.parsed_title == "A Movie"
    assert got.parsed_year == 2020


def test_record_scan_membership(repo, tmp_path):
    scan = repo.start_scan()
    mf = repo.insert_media_file(_mf(tmp_path / "a.mkv"))
    repo.record_scan_membership(scan.id, mf.id)
    members = repo.list_scan_members(scan.id)
    assert mf.id in {m.id for m in members}


# ---------------------------------------------------------------------------
# Missing tracking (FR-806, FR-807)
# ---------------------------------------------------------------------------
def test_mark_missing_and_clear(repo, tmp_path):
    mf = repo.insert_media_file(_mf(tmp_path / "a.mkv"))
    scan_id = repo.start_scan().id

    repo.mark_missing(mf.id, scan_id)
    got = repo.get_media_file(mf.id)
    assert got.missing_since_scan_id == scan_id

    repo.clear_missing(mf.id)
    got = repo.get_media_file(mf.id)
    assert got.missing_since_scan_id is None
