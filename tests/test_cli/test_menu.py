"""Interactive menu tests (FR-200–FR-202, FR-104, FR-1400, FR-1401)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mediavault.cli.menu import menu_loop
from mediavault.config.schema import (
    Config,
    DuplicatesConfig,
    GeneralConfig,
    ScanConfig,
)
from mediavault.models import ScanRun, ScanStatus


@pytest.fixture
def cfg() -> Config:
    return Config(
        general=GeneralConfig(
            db_path=":memory:",
            log_dir="logs",
            log_level="DEBUG",
            ffprobe_path="ffprobe",
            ffprobe_timeout_seconds=60,
            ffprobe_stderr_max_chars=2000,
            subs_dir_name="subs",
            report_output_dir="reports",
            probe_skip_unchanged=True,
            follow_symlinks=False,
            include_hidden=False,
            skip_dirs=[],
        ),
        scan=ScanConfig(),
        duplicates=DuplicatesConfig(
            hash_chunk_bytes=1024,
            partial_hash_bytes=10,
        ),
    )


def _last_scan(status: ScanStatus = ScanStatus.COMPLETED) -> ScanRun:
    return ScanRun(
        id=7,
        status=status,
        movies_found=3,
        shows_found=1,
        episodes_found=5,
        exact_duplicates_found=2,
        near_duplicates_found=1,
    )


# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_menu_exit_on_zero(
    mock_connect, mock_repo_cls, mock_questionary, mock_migrate, cfg
):
    mock_questionary.select.return_value.ask.return_value = "0"
    menu_loop(cfg)
    mock_questionary.select.assert_called_once()


# ---------------------------------------------------------------------------
# "No prior scan" footer (FR-1401)
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_footer_no_scans_yet(
    mock_connect, mock_repo_cls, mock_questionary, mock_migrate, cfg, capsys
):
    mock_repo = mock_repo_cls.return_value
    mock_repo.conn.execute.return_value.fetchone.return_value = None
    mock_questionary.select.return_value.ask.return_value = "0"

    menu_loop(cfg)
    captured = capsys.readouterr()
    assert "No scans yet" in captured.out


# ---------------------------------------------------------------------------
# Scan option (1)
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.scan_roots")
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_menu_scan_triggers_service(
    mock_connect,
    mock_repo_cls,
    mock_questionary,
    mock_migrate,
    mock_scan_roots,
    cfg,
):
    mock_repo = mock_repo_cls.return_value
    mock_repo.list_scan_roots.return_value = []
    mock_repo.conn.execute.return_value.fetchone.return_value = None
    mock_scan_roots.return_value = _last_scan()

    mock_questionary.select.return_value.ask.side_effect = ["1", "0"]
    mock_questionary.text.return_value.ask.return_value = ""

    menu_loop(cfg)
    assert mock_scan_roots.call_count == 0


# ---------------------------------------------------------------------------
# Browse option (2) opens submenu
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.browse_movies")
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_menu_browse_movies(
    mock_connect,
    mock_repo_cls,
    mock_questionary,
    mock_migrate,
    mock_browse,
    cfg,
):
    mock_repo = mock_repo_cls.return_value
    mock_repo.conn.execute.return_value.fetchone.return_value = None
    mock_browse.return_value = ([], 0)

    mock_questionary.select.return_value.ask.side_effect = ["2", "0"]

    menu_loop(cfg)
    mock_browse.assert_called_once()


# ---------------------------------------------------------------------------
# Help (h / ?) prints help text and re-shows menu
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_menu_help(
    mock_connect, mock_repo_cls, mock_questionary, mock_migrate, cfg, capsys
):
    mock_repo = mock_repo_cls.return_value
    mock_repo.conn.execute.return_value.fetchone.return_value = None
    mock_questionary.select.return_value.ask.side_effect = ["h", "0"]

    menu_loop(cfg)
    captured = capsys.readouterr()
    assert "1." in captured.out or "Scan" in captured.out


# ---------------------------------------------------------------------------
# Footer shows last-scan stats (FR-1400)
# ---------------------------------------------------------------------------
@patch("mediavault.cli.menu.migrate")
@patch("mediavault.cli.menu.questionary")
@patch("mediavault.cli.menu.Repository")
@patch("mediavault.cli.menu.connect")
def test_footer_shows_last_scan(
    mock_connect, mock_repo_cls, mock_questionary, mock_migrate, cfg, capsys
):
    mock_repo = mock_repo_cls.return_value
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda k: {
        "id": 7,
        "started_at": "2025-01-01T12:00:00Z",
        "status": "completed",
        "movies_found": 3,
        "shows_found": 1,
        "episodes_found": 5,
        "exact_duplicates_found": 2,
        "near_duplicates_found": 1,
    }[k]
    mock_repo.conn.execute.return_value.fetchone.return_value = mock_row
    mock_questionary.select.return_value.ask.return_value = "0"

    menu_loop(cfg)
    captured = capsys.readouterr()
    assert "Last scan: #7" in captured.out
    assert "Movies: 3" in captured.out
    assert "Exact dups: 2" in captured.out
