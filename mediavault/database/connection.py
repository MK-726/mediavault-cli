"""SQLite connection setup (FR-800, FR-801)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection to the SQLite database at *db_path*.

    Configures:
      * PRAGMA foreign_keys = ON (FR-801)
      * PRAGMA journal_mode = WAL (FR-801)

    Does NOT run migrations; see migrator.migrate().
    """
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")

    return conn
