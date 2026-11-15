"""Database layer (FR-800–FR-811).

Per NFR-015, this is the ONLY package allowed to import ``sqlite3``.
"""

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository

__all__ = ["connect", "migrate", "Repository"]
