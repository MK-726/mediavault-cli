"""DB connection tests (FR-800, FR-801, FR-804)."""

from __future__ import annotations

import sqlite3

from mediavault.database.connection import connect


def test_connect_creates_file_at_path(tmp_path):
    db_path = tmp_path / "mediavault.db"
    conn = connect(db_path)
    try:
        assert db_path.exists()
    finally:
        conn.close()


def test_connect_enables_foreign_keys(tmp_path):
    conn = connect(tmp_path / "m.db")
    try:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_connect_enables_wal(tmp_path):
    conn = connect(tmp_path / "m.db")
    try:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0].lower() == "wal"
    finally:
        conn.close()


def test_connect_returns_sqlite3_connection(tmp_path):
    conn = connect(tmp_path / "m.db")
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_connect_does_not_run_migrations(tmp_path):
    """connect() only opens; migrations are migrator's job (FR-802)."""
    conn = connect(tmp_path / "m.db")
    try:
        row = conn.execute("PRAGMA user_version").fetchone()
        assert row[0] == 0
    finally:
        conn.close()
