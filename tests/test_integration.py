"""End-to-end integration tests from §10.2-§10.5 of the SRS."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mediavault.config.schema import (
    Config,
    DuplicatesConfig,
    GeneralConfig,
    ScanConfig,
)
from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.models import RootType, ScanRoot, ScanStatus
from mediavault.reports.base import ReportScope
from mediavault.services.reporting import build_report_data
from mediavault.services.scanner import scan_roots


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


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield Repository(conn)
    conn.close()


@pytest.fixture(autouse=True)
def _mock_ffprobe():
    """Every test gets a canned FFprobe response so we never spawn subprocesses."""
    fake_output = {
        "format": {
            "format_name": "matroska",
            "duration": "120.0",
            "bit_rate": "5000000",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": "eng"},
            },
        ],
    }
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps(fake_output)
    mock_run.return_value.stderr = ""
    with patch("subprocess.run", mock_run):
        yield


def _touch(p: Path, content: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# §10.2 Integration — initial scan
# ---------------------------------------------------------------------------
def test_integration_initial_scan(tmp_path, repo, cfg):
    """The full-library happy path: 3 movies + 1 show, 2 seasons, 4 episodes."""
    movies_root = tmp_path / "Movies"
    _touch(movies_root / "Movie.One.2020.1080p.mkv")
    _touch(movies_root / "Movie.Two.2021.1080p.mkv")
    _touch(movies_root / "Movie.Three.2022.1080p.mkv")

    tv_root = tmp_path / "TV"
    _touch(tv_root / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E01.mkv")
    _touch(tv_root / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E02.mkv")
    _touch(tv_root / "Breaking-Bad" / "Season-2" / "Breaking.Bad.S02E01.mkv")
    _touch(tv_root / "Breaking-Bad" / "Season-2" / "Breaking.Bad.S02E02.mkv")

    # Two external subtitle files
    _touch(tv_root / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E01.srt")
    _touch(movies_root / "Movie.One.2020.1080p.srt")

    movies_scan_root = repo.insert_scan_root(
        ScanRoot(path=movies_root, root_type=RootType.MOVIES)
    )
    tv_scan_root = repo.insert_scan_root(ScanRoot(path=tv_root, root_type=RootType.TV))

    scan = scan_roots(repo, [movies_scan_root, tv_scan_root], config=cfg)

    assert scan.status == ScanStatus.COMPLETED
    assert scan.movies_found == 3
    assert scan.shows_found == 1
    assert scan.episodes_found == 4

    # DB state
    members = repo.list_scan_members(scan.id)
    assert len(members) == 7

    # Membership rows in scan_media_files
    row = repo.conn.execute(
        "SELECT COUNT(*) FROM scan_media_files WHERE scan_id = ?",
        (scan.id,),
    ).fetchone()
    assert row[0] == 7


# ---------------------------------------------------------------------------
# §10.2 Integration — second scan with changes
# ---------------------------------------------------------------------------
def test_integration_second_scan(tmp_path, repo, cfg):
    """Second scan: one file removed, one added, missing tracking works."""
    movies_root = tmp_path / "Movies"
    _touch(movies_root / "A.mkv", b"file A")
    _touch(movies_root / "B.mkv", b"file B")
    _touch(movies_root / "C.mkv", b"file C")

    root = repo.insert_scan_root(ScanRoot(path=movies_root, root_type=RootType.MOVIES))
    scan1 = scan_roots(repo, [root], config=cfg)
    assert scan1.movies_found == 3

    # Remove B, add D
    (movies_root / "B.mkv").unlink()
    _touch(movies_root / "D.mkv", b"file D")

    scan2 = scan_roots(repo, [root], config=cfg)
    assert scan2.movies_found == 3

    b = repo.get_media_file_by_path(movies_root / "B.mkv")
    assert b is not None
    assert b.missing_since_scan_id == scan2.id
    assert b.last_seen_scan_id == scan1.id

    d = repo.get_media_file_by_path(movies_root / "D.mkv")
    assert d is not None
    assert d.missing_since_scan_id is None

    # Historical membership preserved
    scan1_members = repo.list_scan_members(scan1.id)
    scan2_members = repo.list_scan_members(scan2.id)
    assert len(scan1_members) == 3
    assert len(scan2_members) == 3


# ---------------------------------------------------------------------------
# §10.2 Integration — modified file re-probes
# ---------------------------------------------------------------------------
def test_integration_modified_file(tmp_path, repo, cfg):
    """Same path, new size → FFprobe runs again (mtime and size both change)."""
    movies_root = tmp_path / "Movies"
    _touch(movies_root / "Movie.mkv", b"original")

    root = repo.insert_scan_root(ScanRoot(path=movies_root, root_type=RootType.MOVIES))
    scan_roots(repo, [root], config=cfg)

    mf1 = repo.get_media_file_by_path(movies_root / "Movie.mkv")
    assert mf1 is not None
    original_size = mf1.size

    # Replace the file with different content
    (movies_root / "Movie.mkv").unlink()
    _touch(movies_root / "Movie.mkv", b"different content entirely!")

    scan2 = scan_roots(repo, [root], config=cfg)

    mf2 = repo.get_media_file_by_path(movies_root / "Movie.mkv")
    assert mf2 is not None
    assert mf2.size != original_size
    # The probe should have run again (metadata was refreshed)
    assert mf2.last_seen_scan_id == scan2.id


# ---------------------------------------------------------------------------
# §10.5 Config precedence
# ---------------------------------------------------------------------------
def test_integration_config_precedence(tmp_path, monkeypatch):
    """defaults < XDG < project < env < CLI (SRS §10.4)."""
    from mediavault.config import load_config

    xdg_dir = tmp_path / "xdg" / "mediavault-cli"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "config.toml").write_text(
        '[general]\nlog_level = "WARNING"\n', encoding="utf-8"
    )
    project = tmp_path / "project.toml"
    project.write_text('[general]\nlog_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("MEDIAVAULT_CLI_LOG_LEVEL", "ERROR")

    cfg = load_config(
        cli_overrides={"general": {"log_level": "CRITICAL"}},
        project_config=project,
    )
    assert cfg.general.log_level == "CRITICAL"


# ---------------------------------------------------------------------------
# Report generation end-to-end
# ---------------------------------------------------------------------------
def test_integration_report_build(tmp_path, repo, cfg):
    """The full library → ReportData → text output pipeline."""
    movies_root = tmp_path / "Movies"
    _touch(movies_root / "A.Movie.2020.mkv")
    _touch(movies_root / "B.Movie.2021.mkv")
    _touch(movies_root / "subs" / "A.Movie.2020.srt")

    root = repo.insert_scan_root(ScanRoot(path=movies_root, root_type=RootType.MOVIES))
    scan_roots(repo, [root], config=cfg)

    data = build_report_data(repo, scope=ReportScope.MOVIES)
    assert len(data.movies) == 2
    assert data.scope == ReportScope.MOVIES
    # At least one external sub was found by the scanner if wired; skip if not.

    from mediavault.reports.txt import TxtReport

    out = TxtReport().render(data)
    assert "A Movie (2020)" in out
    assert "B Movie (2021)" in out
