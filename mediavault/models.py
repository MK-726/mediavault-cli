"""In-memory data models (§7, §8).

These are value objects passed between core modules and services. They are
deliberately not an ORM: the repository (mediavault.database.repository)
maps between these and SQLite rows. Keeping them stdlib-only preserves the
import-boundary rule (NFR-015).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


# ---------------------------------------------------------------------------
# Enums mirroring CHECK-constrained columns (FR-810, constants.py)
# ---------------------------------------------------------------------------
class MediaKind(StrEnum):
    MOVIE = "movie"
    EPISODE = "episode"


class ScanStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class SubtitleKind(StrEnum):
    EXTERNAL = "external"
    EMBEDDED = "embedded"


class ParseStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    UNPARSED = "unparsed"


class ParseConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DuplicateKind(StrEnum):
    EXACT = "exact"
    NEAR = "near"


class RootType(StrEnum):
    MOVIES = "movies"
    TV = "tv"
    AUTO = "auto"


# ---------------------------------------------------------------------------
# Scan roots and scan runs (FR-100, FR-102)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ScanRoot:
    path: Path
    root_type: RootType
    id: int | None = None
    added_at: str | None = None  # ISO-8601, set by repository
    last_scan_id: int | None = None


@dataclass(slots=True)
class ScanRun:
    """A single scan execution (FR-102).

    Counters are mutable because the scanner updates them as it progresses.
    """

    id: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    status: ScanStatus = ScanStatus.RUNNING

    movies_found: int = 0
    shows_found: int = 0
    episodes_found: int = 0
    exact_duplicates_found: int = 0
    near_duplicates_found: int = 0

    filesystem_errors: int = 0
    probe_errors: int = 0
    hash_errors: int = 0

    @property
    def errors_count(self) -> int:
        """Aggregate error counter (FR-102)."""
        return self.filesystem_errors + self.probe_errors + self.hash_errors


# ---------------------------------------------------------------------------
# Media files, movies, shows, seasons, episodes (§8)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class MediaFile:
    """A discovered video file and its parsed + probed metadata.

    ``path`` is the identity in v1 (FR-805). ``size`` and ``mtime_ns``
    drive cache invalidation (FR-500, FR-504) and staged hashing (FR-701).
    """

    path: Path
    filename: str
    extension: str  # lowercase, with dot (".mkv")
    kind: MediaKind
    size: int
    mtime_ns: int

    # identity (assigned by repository on insert)
    id: int | None = None
    last_seen_scan_id: int | None = None
    missing_since_scan_id: int | None = None

    # parsed metadata (FR-403, FR-808)
    parsed_title: str | None = None  # display form
    parsed_year: int | None = None
    parse_status: ParseStatus = ParseStatus.UNPARSED
    parse_confidence: ParseConfidence = ParseConfidence.LOW

    # episode identity (parsed)
    show_key: str | None = None  # match key, e.g. "breaking_bad"
    season: int | None = None
    episode: int | None = None

    # near-duplicate key (FR-713)
    near_dup_key: str | None = None

    # probed metadata (FR-501–FR-502)
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    bit_rate: int | None = None
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_streams_json: str | None = None
    has_embedded_subs: bool | None = None  # None = unknown (FR-507)
    embedded_sub_count: int | None = None
    embedded_sub_langs: str | None = None  # comma-separated
    probed_at: str | None = None
    ffprobe_version: str | None = None


@dataclass(frozen=True, slots=True)
class Movie:
    """Link/attribute table row only (FR-803, §8).

    No title duplication: the title lives on MediaFile.parsed_title.
    ``franchise`` is the single-level subdirectory name under a movies root
    (FR-310), or None.
    """

    media_file_id: int
    franchise: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Show:
    show_key: str  # match key: lowercased, underscore-separated (FR-410)
    display_name: str  # display: whitespace-separated, title-case
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Season:
    show_id: int
    number: int
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Episode:
    media_file_id: int
    show_id: int
    season_id: int | None
    episode_number: int | None
    id: int | None = None


# ---------------------------------------------------------------------------
# Subtitles (FR-600–FR-606)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Subtitle:
    media_file_id: int
    kind: SubtitleKind
    path: Path | None = None  # None for embedded (FR-602)
    is_primary: bool = False
    missing_since_scan_id: int | None = None
    id: int | None = None


# ---------------------------------------------------------------------------
# Duplicates (FR-700–FR-714)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    scan_id: int
    kind: DuplicateKind
    id: int | None = None


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    group_id: int
    media_file_id: int
    # SHA-256 hex; retained for near-dup annotation (FR-711)
    hash_value: str | None = None


# ---------------------------------------------------------------------------
# Discovery/parse hand-off containers (used by services/scanner.py, Phase 7)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DiscoveryResult:
    """Result of one root's discovery pass (FR-310–FR-314)."""

    root: ScanRoot
    media_files: list[MediaFile] = field(default_factory=list)
    orphan_subtitles: list[Path] = field(default_factory=list)
    # human-readable, already logged
    errors: list[str] = field(default_factory=list)
