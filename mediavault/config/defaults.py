"""Built-in default configuration values (§9.1)."""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    "general": {
        "db_path": "~/.local/share/mediavault-cli/mediavault.db",
        "log_dir": "~/.local/state/mediavault-cli/logs",
        "log_level": "INFO",
        "ffprobe_path": "ffprobe",
        "ffprobe_timeout_seconds": 60,
        "ffprobe_stderr_max_chars": 2000,
        "subs_dir_name": "subs",
        "report_output_dir": "~/.local/share/mediavault-cli/reports",
        "probe_skip_unchanged": True,
        "follow_symlinks": False,
        "include_hidden": False,
        "skip_dirs": [
            "@eaDir",
            "#recycle",
            ".Trash-*",
            "$RECYCLE.BIN",
            "System Volume Information",
        ],
    },
    "scan": {
        "default_roots": [],
    },
    "duplicates": {
        "hash_chunk_bytes": 1048576,
        "partial_hash_bytes": 65536,
    },
}
