"""Configuration precedence resolution (FR-1200, FR-1208).

Precedence (highest first):
  1. CLI flags (passed as overrides)
  2. Environment variables (prefix MEDIAVAULT_CLI_)
  3. Project-local config
  4. ~/.config/mediavault-cli/config.toml (XDG)
  5. Built-in defaults
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any, Final

from mediavault.config import defaults as _defaults
from mediavault.config.schema import Config
from mediavault.errors import ConfigurationError


class _Unset:
    """Sentinel: use the standard project-config resolution rule."""
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "UNSET"


_UNSET: Final = _Unset()

ENV_PREFIX = "MEDIAVAULT_CLI_"

# Env var → dotted key path. Only these are env-overridable in v1 (FR-1206).
_ENV_MAP: dict[str, tuple[str, ...]] = {
    "MEDIAVAULT_CLI_DB_PATH": ("general", "db_path"),
    "MEDIAVAULT_CLI_LOG_DIR": ("general", "log_dir"),
    "MEDIAVAULT_CLI_LOG_LEVEL": ("general", "log_level"),
    "MEDIAVAULT_CLI_FFPROBE_PATH": ("general", "ffprobe_path"),
}

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge *overlay* into *base*, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_toml(path: Path) -> dict:
    """Read a TOML file; return {} if missing; raise ConfigurationError if malformed."""
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigurationError(f"invalid config file {path}: {exc}") from exc


def _xdg_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "mediavault-cli" / "config.toml"


def _project_config_path() -> Path | None:
    """Return the project-local config path, or None if suppressed.

    If MEDIAVAULT_CLI_CONFIG is set, it *replaces* ./config.toml (FR-1200).
    """
    override = os.environ.get("MEDIAVAULT_CLI_CONFIG")
    if override:
        return Path(override).expanduser()
    candidate = Path.cwd() / "config.toml"
    return candidate if candidate.exists() else None


def _env_overrides() -> dict:
    """Collect env-var overrides into a nested dict."""
    overlay: dict[str, Any] = {}
    for env_name, key_path in _ENV_MAP.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        node = overlay
        for part in key_path[:-1]:
            node = node.setdefault(part, {})
        node[key_path[-1]] = value
    return overlay


def _validate(config: Config) -> None:
    g = config.general
    if g.log_level.upper() not in _VALID_LOG_LEVELS:
        raise ConfigurationError(
            f"general.log_level must be one of {sorted(_VALID_LOG_LEVELS)}; "
            f"got {g.log_level!r}"
        )
    if g.ffprobe_timeout_seconds <= 0:
        raise ConfigurationError(
            f"general.ffprobe_timeout_seconds must be > 0; "
            f"got {g.ffprobe_timeout_seconds!r}"
        )
    if g.ffprobe_stderr_max_chars < 0:
        raise ConfigurationError(
            f"general.ffprobe_stderr_max_chars must be >= 0; "
            f"got {g.ffprobe_stderr_max_chars!r}"
        )
    d = config.duplicates
    if d.hash_chunk_bytes <= 0 or d.partial_hash_bytes <= 0:
        raise ConfigurationError(
            "duplicates.hash_chunk_bytes and partial_hash_bytes must be > 0"
        )


def load_config(
    *,
    cli_overrides: dict | None = None,
    project_config: Path | None | _Unset = _UNSET,
) -> Config:
    """Resolve and validate the application configuration.

    Parameters
    ----------
    cli_overrides:
        Nested dict of values from CLI flags (highest precedence). Optional.
    project_config:
        Explicit project-local config path (mainly for tests). The default
        sentinel means "use the standard resolution rule" (MEDIAVAULT_CLI_CONFIG
        or ./config.toml). Pass ``None`` to force *no* project-local source.
    """
    # 1. defaults
    resolved = copy.deepcopy(_defaults.DEFAULTS)

    # 2. XDG
    resolved = _deep_merge(resolved, _read_toml(_xdg_config_path()))

    # 3. project-local (selection rule per FR-1200)
    if isinstance(project_config, _Unset):
        project_path: Path | None = _project_config_path()
    else:
        project_path = project_config

    if project_path is not None:
        resolved = _deep_merge(resolved, _read_toml(project_path))

    # 4. env
    resolved = _deep_merge(resolved, _env_overrides())

    # 5. CLI flags
    if cli_overrides:
        resolved = _deep_merge(resolved, cli_overrides)

    config = Config.from_dict(resolved)
    _validate(config)
    return config
