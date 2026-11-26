"""Integration tests for duplicate detection during scan."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.config import load_config
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.models import RootType, ScanRoot
from mediavault.services.scanner import scan_roots


@pytest.fixture
def cfg(tmp_path):
    # Small chunk sizes so duplicate detection triggers on tiny files
    import os

    for k in list(os.environ):
        if k.startswith("MEDIAVAULT_CLI_"):
            os.environ.pop(k, None)
    cfg = load_config(project_config=None)
    object.__setattr__(cfg.duplicates, "hash_chunk_bytes", 4)
    object.__setattr__(cfg.duplicates, "partial_hash_bytes", 2)
    return cfg


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield Repository(conn)
    conn.close()


def _touch(p: Path, content: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_scan_detects_and_persists_exact_duplicates(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    # Two identical files, one different
    _touch(movies / "A.Movie.2020.mkv", b"identical content")
    _touch(movies / "A.Movie.2020.copy.mkv", b"identical content")
    _touch(movies / "B.Movie.2021.mkv", b"different content")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan = scan_roots(repo, [root], config=cfg)

    # Check counters
    assert scan.exact_duplicates_found == 1

    # Check DB
    rows = repo.conn.execute("SELECT * FROM duplicate_groups").fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == "exact"

    members = repo.conn.execute(
        "SELECT * FROM duplicate_members WHERE group_id = ?", (rows[0]["id"],)
    ).fetchall()
    assert len(members) == 2


def test_scan_detects_near_duplicates(tmp_path, repo, cfg):
    movies = tmp_path / "movies"
    # Same title, different content (different quality)
    _touch(movies / "A.Movie.2020.1080p.mkv", b"content A")
    _touch(movies / "A.Movie.2020.2160p.mkv", b"content B")

    root = repo.insert_scan_root(ScanRoot(path=movies, root_type=RootType.MOVIES))
    scan = scan_roots(repo, [root], config=cfg)

    # Check counters
    assert scan.near_duplicates_found == 1

    # Check DB
    rows = repo.conn.execute("SELECT * FROM duplicate_groups").fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == "near"
