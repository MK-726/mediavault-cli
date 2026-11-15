"""Schema DDL tests (FR-803, FR-810, FR-811)."""

from __future__ import annotations

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield conn
    conn.close()


def _tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _indexes(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {r[0] for r in rows}


def test_all_required_tables_exist(db):
    required = {
        "scan_roots",
        "scans",
        "scan_roots_scanned",
        "media_files",
        "scan_media_files",
        "movies",
        "shows",
        "seasons",
        "episodes",
        "subtitles",
        "duplicate_groups",
        "duplicate_members",
        "meta",
    }
    assert required <= _tables(db)


def test_media_files_check_constraint(db):
    """FR-810: kind ∈ {movie, episode}."""
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO media_files (path, filename, extension, kind, size, mtime_ns) "
            "VALUES ('/x.mkv','x.mkv','.mkv','invalid',1,2)"
        )


def test_scans_status_check(db):
    """FR-810: status ∈ {running, completed, partial, failed}."""
    with pytest.raises(Exception):
        db.execute("INSERT INTO scans (status) VALUES ('nope')")


def test_media_files_path_unique(db):
    db.execute(
        "INSERT INTO media_files (path, filename, extension, kind, size, mtime_ns) "
        "VALUES ('/x.mkv','x.mkv','.mkv','movie',1,2)"
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO media_files (path, filename, extension, kind, size, mtime_ns) "
            "VALUES ('/x.mkv','x.mkv','.mkv','movie',1,2)"
        )


def test_foreign_key_enforced(db):
    """FR-810: FK violations rejected."""
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO scan_media_files (scan_id, media_file_id) VALUES (99, 99)"
        )


def test_expected_indexes_exist(db):
    """FR-811: required indexes present."""
    expected = {
        "ix_media_files_last_seen",
        "ix_media_files_missing_since",
        "ix_media_files_kind",
        "ix_media_files_near_dup_key",
        "ix_media_files_parsed_title",
        "ix_media_files_parsed_year",
        "ix_episodes_show",
        "ix_episodes_season",
        "ix_duplicate_groups_scan",
        "ix_scan_media_files_scan",
    }
    assert expected <= _indexes(db)


def test_meta_table_has_expected_keys(db):
    rows = db.execute("SELECT key FROM meta").fetchall()
    keys = {r[0] for r in rows}
    assert {"schema_version", "ffprobe_version"} <= keys
