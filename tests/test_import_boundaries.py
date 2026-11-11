"""Architectural import-boundary enforcement (NFR-015, §7).

Rules:
  (a) Only mediavault.database may import sqlite3.
  (b) Core modules must not import typer / rich / questionary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "mediavault"

UI_MODULES = {"typer", "rich", "questionary"}
CORE_MODULES = {"discovery", "parsing", "metadata", "subtitles", "duplicates"}
DB_PACKAGE = "database"


def _iter_py_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _imported_top_level_names(path: Path) -> set[str]:
    """Return the top-level module names imported by *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (node.level > 0) have no top-level name.
            if node.level == 0 and node.module:
                names.add(node.module.split(".", 1)[0])
    return names


def _relative_parts(path: Path) -> tuple[str, ...]:
    """
    Path components relative to the package root (e.g. ('database','connection.py')).
    """
    return path.relative_to(PACKAGE_ROOT).parts


def test_only_database_package_imports_sqlite3():
    offenders: list[str] = []
    for path in _iter_py_files():
        parts = _relative_parts(path)
        in_db_package = len(parts) > 1 and parts[0] == DB_PACKAGE
        if "sqlite3" in _imported_top_level_names(path) and not in_db_package:
            offenders.append(str(path.relative_to(PACKAGE_ROOT.parent)))
    assert not offenders, (
        "sqlite3 may only be imported inside mediavault.database; "
        f"found violations: {offenders}"
    )


@pytest.mark.parametrize("core_name", sorted(CORE_MODULES))
def test_core_modules_do_not_import_ui_or_cli(core_name: str):
    path = PACKAGE_ROOT / f"{core_name}.py"
    if not path.exists():
        pytest.skip(f"core module not yet implemented: {path.name}")

    imported = _imported_top_level_names(path)
    forbidden = imported & UI_MODULES
    assert not forbidden, (
        f"{path.name} must not import {sorted(forbidden)} "
        f"(core modules are UI-agnostic; see §7)"
    )
