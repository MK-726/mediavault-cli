"""Schema migration runner (FR-802, FR-802a)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from mediavault.errors import MigrationError
from mediavault.logging_setup import get_logger

_log = get_logger("database.migrator")

_MIGRATION_RE = re.compile(r"^(\d+)_")


def _get_applied_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_applied_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version};")


def _discover_migrations(migrations_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted (version, path) tuples."""
    if not migrations_dir.exists():
        return []

    migrations = []
    for p in migrations_dir.glob("*.sql"):
        m = _MIGRATION_RE.match(p.name)
        if not m:
            _log.warning("migrator: skipping malformed filename %s", p.name)
            continue
        version = int(m.group(1))
        migrations.append((version, p))

    migrations.sort(key=lambda x: x[0])
    return migrations


def migrate(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> None:
    """Apply pending migrations to *conn*.

    Implements FR-802a:
      * ordered execution
      * per-migration transaction
      * refusal to run if DB is newer than code
      * rollback on failure
    """

    def _split_sql_statements(sql: str) -> list[str]:
        """Split a SQL script into individual statements, ignoring comments."""
        # Strip single-line comments
        lines = [line.split("--")[0] for line in sql.splitlines()]
        cleaned_sql = "\n".join(lines)

        # Split by semicolon and filter out empty strings
        return [stmt.strip() for stmt in cleaned_sql.split(";") if stmt.strip()]

    if migrations_dir is None:
        migrations_dir = Path(__file__).parent / "migrations"

    current_version = _get_applied_version(conn)
    available = _discover_migrations(migrations_dir)

    if not available:
        return

    latest_available = available[-1][0]

    if current_version > latest_available:
        raise MigrationError(
            f"database schema version ({current_version}) is newer than "
            f"the latest known version ({latest_available}). "
            "Upgrade MediaVault to open this database."
        )

    for version, path in available:
        if version <= current_version:
            continue

        _log.info("migrator: applying %s (version %d)", path.name, version)
        sql = path.read_text(encoding="utf-8")

        try:
            # Use a standard Python transaction block. Because we execute
            # the SQL statements individually below (instead of using
            # executescript), Python's sqlite3 module will correctly
            # manage the BEGIN/COMMIT and rollback on exceptions.
            with conn:
                # Execute each statement individually to avoid executescript's
                # forced auto-commit behavior.
                for statement in _split_sql_statements(sql):
                    if statement.strip():
                        conn.execute(statement)

                # Update the version inside the same transaction.
                _set_applied_version(conn, version)

            _log.info("migrator: successfully applied version %d", version)
            current_version = version

        except Exception as exc:
            _log.error("migrator: failed to apply %s: %s", path.name, exc)
            raise MigrationError(f"Migration failed on {path.name}: {exc}") from exc
