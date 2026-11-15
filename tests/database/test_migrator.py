"""Migration runner tests (FR-802, FR-802a)."""

from __future__ import annotations

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.errors import MigrationError


def test_fresh_db_gets_migrated(tmp_path):
    conn = connect(tmp_path / "m.db")
    try:
        migrate(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version >= 1
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    conn = connect(tmp_path / "m.db")
    try:
        migrate(conn)
        v1 = conn.execute("PRAGMA user_version").fetchone()[0]
        migrate(conn)  # run again
        v2 = conn.execute("PRAGMA user_version").fetchone()[0]
        assert v1 == v2
    finally:
        conn.close()


def test_migrate_refuses_future_version(tmp_path):
    """If user_version > latest known, refuse (FR-802a)."""
    conn = connect(tmp_path / "m.db")
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
        with pytest.raises(MigrationError, match="newer"):
            migrate(conn)
    finally:
        conn.close()


def test_migration_failure_rolls_back(tmp_path, monkeypatch):
    """A failing migration leaves the DB at the previous version (FR-802a)."""

    # Create a broken migration appended after the real ones.
    broken_dir = tmp_path / "broken_migrations"
    broken_dir.mkdir()
    (broken_dir / "0001_init.sql").write_text("CREATE TABLE t(x);", encoding="utf-8")
    (broken_dir / "0099_broken.sql").write_text("THIS IS NOT SQL;", encoding="utf-8")

    conn = connect(tmp_path / "m.db")
    try:
        with pytest.raises(MigrationError):
            migrate(conn, migrations_dir=broken_dir)
        # 0001 applied; 0099 rolled back
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 1
    finally:
        conn.close()
