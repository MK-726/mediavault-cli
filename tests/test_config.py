"""Config precedence and validation tests (FR-1200–FR-1208, §10.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.config import load_config
from mediavault.errors import ConfigurationError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Isolate each test from real env vars and XDG/HOME."""
    for name in list(__import__("os").environ):
        if name.startswith("MEDIAVAULT_CLI_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _write_toml(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_only():
    cfg = load_config(project_config=None)
    assert cfg.general.log_level == "INFO"
    assert cfg.general.ffprobe_path == "ffprobe"
    assert cfg.duplicates.hash_chunk_bytes == 1048576


def test_full_precedence_chain(tmp_path, monkeypatch):
    """defaults < XDG < project < env < CLI ⇒ CLI wins (§10.4)."""
    # XDG
    xdg = tmp_path / "xdg" / "mediavault-cli" / "config.toml"
    _write_toml(xdg, '[general]\nlog_level = "WARNING"\n')
    # project
    project = _write_toml(tmp_path / "project.toml", '[general]\nlog_level = "DEBUG"\n')
    # env
    monkeypatch.setenv("MEDIAVAULT_CLI_LOG_LEVEL", "ERROR")

    cfg = load_config(
        cli_overrides={"general": {"log_level": "CRITICAL"}},
        project_config=project,
    )
    assert cfg.general.log_level == "CRITICAL"


def test_env_beats_project(tmp_path, monkeypatch):
    project = _write_toml(tmp_path / "project.toml", '[general]\nlog_level = "DEBUG"\n')
    monkeypatch.setenv("MEDIAVAULT_CLI_LOG_LEVEL", "ERROR")
    cfg = load_config(project_config=project)
    assert cfg.general.log_level == "ERROR"


def test_project_beats_xdg(tmp_path):
    xdg = tmp_path / "xdg" / "mediavault-cli" / "config.toml"
    _write_toml(xdg, '[general]\nlog_level = "WARNING"\n')
    project = _write_toml(tmp_path / "project.toml", '[general]\nlog_level = "DEBUG"\n')
    cfg = load_config(project_config=project)
    assert cfg.general.log_level == "DEBUG"


def test_mediavault_cli_config_replaces_project_toml(tmp_path, monkeypatch):
    """MEDIAVAULT_CLI_CONFIG replaces ./config.toml (FR-1200)."""
    _write_toml(Path.cwd() / "config.toml", '[general]\nlog_level = "DEBUG"\n')
    override = _write_toml(
        tmp_path / "override.toml", '[general]\nlog_level = "ERROR"\n'
    )
    monkeypatch.setenv("MEDIAVAULT_CLI_CONFIG", str(override))

    cfg = load_config()  # use standard rule; should read override, not ./config.toml
    assert cfg.general.log_level == "ERROR"


def test_missing_mediavault_cli_config_treated_as_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAVAULT_CLI_CONFIG", str(tmp_path / "nope.toml"))
    cfg = load_config()
    assert cfg.general.log_level == "INFO"  # falls through to defaults


def test_invalid_toml_raises(tmp_path):
    bad = _write_toml(tmp_path / "bad.toml", "not [valid toml")
    with pytest.raises(ConfigurationError):
        load_config(project_config=bad)


def test_schema_violation_raises(tmp_path):
    bad = _write_toml(
        tmp_path / "bad.toml",
        '[general]\nlog_level = "NOT_A_LEVEL"\n',
    )
    with pytest.raises(ConfigurationError):
        load_config(project_config=bad)


def test_wrong_type_raises(tmp_path):
    bad = _write_toml(tmp_path / "bad.toml", "[duplicates]\nhash_chunk_bytes = 0\n")
    with pytest.raises(ConfigurationError):
        load_config(project_config=bad)
