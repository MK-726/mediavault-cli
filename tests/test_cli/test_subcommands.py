"""CLI subcommand tests (FR-200–FR-209)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mediavault.cli.main import app
from mediavault.config.schema import (
    Config,
    DuplicatesConfig,
    GeneralConfig,
    ScanConfig,
)
from mediavault.errors import UsageError
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
    ScanRun,
    ScanStatus,
)

runner = CliRunner()


def _dummy_movie() -> MediaFile:
    return MediaFile(
        path=Path("/lib/a.mkv"),
        filename="a.mkv",
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=1,
        id=1,
        parsed_title="A Movie",
        parsed_year=2020,
        parse_status=ParseStatus.OK,
        parse_confidence=ParseConfidence.HIGH,
        codec="h264",
        width=1920,
        height=1080,
        duration=120.0,
    )


@pytest.fixture(autouse=True)
def _patch_cli_dependencies():
    """Patch load_config and migrate for all commands."""
    cfg = Config(
        general=GeneralConfig(
            db_path="m.db",
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
    with (
        patch("mediavault.cli.main.load_config", return_value=cfg),
        patch("mediavault.cli.commands.scan.migrate"),
        patch("mediavault.cli.commands.browse.migrate"),
        patch("mediavault.cli.commands.search.migrate"),
        patch("mediavault.cli.commands.export.migrate"),
        patch("mediavault.cli.commands.analyze.migrate"),
    ):
        yield


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.scan.scan_roots")
@patch("mediavault.cli.commands.scan.Repository")
@patch("mediavault.cli.commands.scan.connect")
def test_scan_command(mock_connect, mock_repo_cls, mock_scan_roots, tmp_path):
    mock_scan_roots.return_value = ScanRun(
        id=1,
        status=ScanStatus.COMPLETED,
        movies_found=5,
        shows_found=1,
        episodes_found=3,
    )
    result = runner.invoke(app, ["scan", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Scan completed" in result.stdout
    assert "Movies: 5" in result.stdout


# ---------------------------------------------------------------------------
# Browse
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.browse.browse_movies")
@patch("mediavault.cli.commands.browse.Repository")
@patch("mediavault.cli.commands.browse.connect")
def test_browse_movies(mock_connect, mock_repo_cls, mock_browse):
    mock_browse.return_value = ([_dummy_movie()], 1)
    result = runner.invoke(app, ["browse", "movies"])
    assert result.exit_code == 0
    assert "A Movie" in result.stdout
    assert "2020" in result.stdout


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.search.svc_search")
@patch("mediavault.cli.commands.search.Repository")
@patch("mediavault.cli.commands.search.connect")
def test_search_command(mock_connect, mock_repo, mock_search):
    mock_search.return_value = ([_dummy_movie()], 1)
    result = runner.invoke(app, ["search", "--title", "A Movie"])
    assert result.exit_code == 0
    assert "A Movie" in result.stdout


@patch("mediavault.cli.commands.search.svc_search")
@patch("mediavault.cli.commands.search.Repository")
@patch("mediavault.cli.commands.search.connect")
def test_search_command_conflict_usage_error(mock_connect, mock_repo, mock_search):
    mock_search.side_effect = UsageError("Conflicting subtitle filters")
    result = runner.invoke(app, ["search", "--has-subs", "--no-subs"])
    assert result.exit_code == 2
    assert "Conflicting" in result.stdout


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.export.export_reports")
@patch("mediavault.cli.commands.export.build_report_data")
@patch("mediavault.cli.commands.export.Repository")
@patch("mediavault.cli.commands.export.connect")
def test_export_command(mock_connect, mock_repo, mock_build, mock_export, tmp_path):
    mock_export.return_value = [tmp_path / "report.txt"]
    result = runner.invoke(app, ["export", "--format", "txt"])
    assert result.exit_code == 0
    assert "Exported 1 file" in result.stdout
    assert "report.txt" in result.stdout


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.analyze.analyze_codecs")
@patch("mediavault.cli.commands.analyze.Repository")
@patch("mediavault.cli.commands.analyze.connect")
def test_analyze_command(mock_connect, mock_repo, mock_analyze):
    from mediavault.models import CodecReport, CodecRow

    mock_analyze.return_value = CodecReport(
        rows=(CodecRow(codec="h264", kind="movie", count=5),),
        total_files=5,
    )
    result = runner.invoke(app, ["analyze", "codecs"])
    assert result.exit_code == 0
    assert "h264" in result.stdout
    assert "5" in result.stdout
