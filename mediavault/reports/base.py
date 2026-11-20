"""Base types for report generation (FR-1100–FR-1104)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from mediavault.models import MediaFile


class ReportScope(StrEnum):
    FULL = "full"
    MOVIES = "movies"
    SHOW = "show"


@dataclass(frozen=True, slots=True)
class ReportData:
    """The fully queried and filtered data ready for rendering."""

    scope: ReportScope

    movies: tuple[MediaFile, ...]
    episodes: tuple[MediaFile, ...]

    # Set of media_file.id values that have ≥1 external subtitle.
    # Used by TXT/MD formatters to render the hybrid 'subs' column.
    files_with_external_subs: frozenset[int] = frozenset()

    # ISO 8601 timestamp; the CLI runner fills this in Phase 15.
    # Formatters render it only when non-empty.
    generated_at: str = ""

    # Problem sections (FR-1104)
    orphan_subtitles: tuple[Path, ...] = ()
    movies_without_external_subs: tuple[MediaFile, ...] = ()
    unparsed_files: tuple[MediaFile, ...] = ()
    probe_error_files: tuple[MediaFile, ...] = ()
    missing_files: tuple[MediaFile, ...] = ()


class Report(Protocol):
    """Protocol for report formatters."""

    def render(self, data: ReportData) -> str:
        """Render the report data to a string."""
        ...

    def write(self, data: ReportData, path: Path) -> None:
        """Render and write the report to *path*."""
        ...
