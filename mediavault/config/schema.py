"""Typed configuration schema (FR-1202, FR-1208)."""

from __future__ import annotations

from dataclasses import dataclass, field

from mediavault.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class GeneralConfig:
    db_path: str
    log_dir: str
    log_level: str
    ffprobe_path: str
    ffprobe_timeout_seconds: int
    ffprobe_stderr_max_chars: int
    subs_dir_name: str
    report_output_dir: str
    probe_skip_unchanged: bool
    follow_symlinks: bool
    include_hidden: bool
    skip_dirs: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScanConfig:
    default_roots: list[dict] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DuplicatesConfig:
    hash_chunk_bytes: int
    partial_hash_bytes: int


@dataclass(frozen=True, slots=True)
class Config:
    general: GeneralConfig
    scan: ScanConfig
    duplicates: DuplicatesConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        try:
            return cls(
                general=GeneralConfig(**data["general"]),
                scan=ScanConfig(**data.get("scan", {})),
                duplicates=DuplicatesConfig(**data["duplicates"]),
            )
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"configuration schema violation: {exc}") from exc
