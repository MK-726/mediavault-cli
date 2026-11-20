"""Config subcommand tests (FR-1203–FR-1205)."""

from __future__ import annotations

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

runner = CliRunner()


@pytest.fixture
def mock_cfg() -> Config:
    return Config(
        general=GeneralConfig(
            db_path="~/.local/share/mediavault-cli/mediavault.db",
            log_dir="~/.local/state/mediavault-cli/logs",
            log_level="INFO",
            ffprobe_path="ffprobe",
            ffprobe_timeout_seconds=60,
            ffprobe_stderr_max_chars=2000,
            subs_dir_name="subs",
            report_output_dir="~/.local/share/mediavault-cli/reports",
            probe_skip_unchanged=True,
            follow_symlinks=False,
            include_hidden=False,
            skip_dirs=[],
        ),
        scan=ScanConfig(),
        duplicates=DuplicatesConfig(
            hash_chunk_bytes=1048576,
            partial_hash_bytes=65536,
        ),
    )


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.config_cmd.load_config")
def test_config_show(mock_load_config, mock_cfg, monkeypatch):
    mock_load_config.return_value = mock_cfg
    monkeypatch.setenv("COLUMNS", "200")  # Force a wide terminal

    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "db_path" in result.stdout
    assert "~/.local/share/mediavault-cli/mediavault.db" in result.stdout
    assert "log_level" in result.stdout


# ---------------------------------------------------------------------------
# config paths
# ---------------------------------------------------------------------------
@patch("mediavault.cli.commands.config_cmd.load_config")
def test_config_paths(mock_load_config, mock_cfg):
    mock_load_config.return_value = mock_cfg
    result = runner.invoke(app, ["config", "paths"])
    assert result.exit_code == 0
    assert "DB Path:" in result.stdout
    assert "Report Dir:" in result.stdout
    assert "mediavault.db" in result.stdout


# ---------------------------------------------------------------------------
# config init
# ---------------------------------------------------------------------------
def test_config_init_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").exists()
    assert "Created" in result.stdout


def test_config_init_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("# existing")
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_config_init_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("# existing")
    result = runner.invoke(app, ["config", "init", "--force"])
    assert result.exit_code == 0
    content = (tmp_path / "config.toml").read_text()
    assert "[general]" in content
