"""CSV report formatter (FR-1102–FR-1106).

Writes three separate files per export:
    <base>-movies.csv    (only when scope includes movies)
    <base>-episodes.csv  (only when scope includes episodes)
    <base>-problems.csv  (always)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from mediavault.models import MediaFile
from mediavault.reports.base import ReportData, ReportScope

_MOVIE_HEADERS = [
    "title",
    "year",
    "resolution",
    "codec",
    "duration_s",
    "has_external_subs",
    "has_embedded_subs",
    "duplicate_group",
    "path",
]
_EPISODE_HEADERS = [
    "show",
    "season",
    "episode",
    "resolution",
    "codec",
    "duration_s",
    "has_external_subs",
    "has_embedded_subs",
    "duplicate_group",
    "path",
]
_PROBLEM_HEADERS = ["kind", "path", "detail"]


def _bool(b: bool | None) -> str:
    return "true" if b else "false"


def _resolution(w: int | None, h: int | None) -> str:
    return f"{w}x{h}" if w and h else "unknown"


def _movie_row(m: MediaFile, has_ext: bool) -> dict[str, str]:
    return {
        "title": m.parsed_title or "",
        "year": str(m.parsed_year) if m.parsed_year else "",
        "resolution": _resolution(m.width, m.height),
        "codec": m.codec or "",
        "duration_s": f"{m.duration:.1f}" if m.duration else "",
        "has_external_subs": _bool(has_ext),
        "has_embedded_subs": _bool(m.has_embedded_subs),
        "duplicate_group": "",
        "path": str(m.path),
    }


def _episode_row(e: MediaFile, has_ext: bool) -> dict[str, str]:
    return {
        "show": e.parsed_title or e.show_key or "",
        "season": str(e.season) if e.season else "",
        "episode": str(e.episode) if e.episode else "",
        "resolution": _resolution(e.width, e.height),
        "codec": e.codec or "",
        "duration_s": f"{e.duration:.1f}" if e.duration else "",
        "has_external_subs": _bool(has_ext),
        "has_embedded_subs": _bool(e.has_embedded_subs),
        "duplicate_group": "",
        "path": str(e.path),
    }


def _csv_string(headers: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=headers,
        quoting=csv.QUOTE_ALL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


class CsvReport:
    """CSV report renderer producing three files per export."""

    def render_movies(self, data: ReportData) -> str:
        ext = data.files_with_external_subs
        rows = [_movie_row(m, m.id in ext) for m in data.movies]
        return _csv_string(_MOVIE_HEADERS, rows)

    def render_episodes(self, data: ReportData) -> str:
        ext = data.files_with_external_subs
        rows = [_episode_row(e, e.id in ext) for e in data.episodes]
        return _csv_string(_EPISODE_HEADERS, rows)

    def render_problems(self, data: ReportData) -> str:
        rows: list[dict[str, str]] = []
        for p in data.orphan_subtitles:
            rows.append({"kind": "orphan_subtitle", "path": str(p), "detail": ""})
        for m in data.unparsed_files:
            rows.append({"kind": "unparsed", "path": str(m.path), "detail": ""})
        for m in data.probe_error_files:
            rows.append({"kind": "probe_error", "path": str(m.path), "detail": ""})
        for m in data.missing_files:
            rows.append({"kind": "missing", "path": str(m.path), "detail": ""})
        return _csv_string(_PROBLEM_HEADERS, rows)

    def write(self, data: ReportData, base_path: Path) -> list[Path]:
        """Write CSV files with *base_path* prefix. Returns paths written.

        Produces:
            <base>-movies.csv    (if scope in {FULL, MOVIES})
            <base>-episodes.csv  (if scope in {FULL, SHOW})
            <base>-problems.csv  (always)
        """
        written: list[Path] = []

        if data.scope in (ReportScope.FULL, ReportScope.MOVIES):
            movies_path = base_path.with_name(f"{base_path.name}-movies.csv")
            movies_path.write_text(self.render_movies(data), encoding="utf-8")
            written.append(movies_path)

        if data.scope in (ReportScope.FULL, ReportScope.SHOW):
            episodes_path = base_path.with_name(f"{base_path.name}-episodes.csv")
            episodes_path.write_text(self.render_episodes(data), encoding="utf-8")
            written.append(episodes_path)

        problems_path = base_path.with_name(f"{base_path.name}-problems.csv")
        problems_path.write_text(self.render_problems(data), encoding="utf-8")
        written.append(problems_path)

        return written
