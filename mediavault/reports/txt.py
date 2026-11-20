"""TXT report formatter (FR-1102–FR-1104, FR-1108)."""

from __future__ import annotations

from pathlib import Path

from mediavault.models import MediaFile
from mediavault.reports.base import ReportData


def _format_movie(m: MediaFile) -> list[str]:
    """Format a single movie block."""
    title = m.parsed_title or "(untitled)"
    year = f" ({m.parsed_year})" if m.parsed_year else ""
    res = f"{m.width}x{m.height}" if m.width else "unknown"
    codec = m.codec or "unknown"
    dur = f"{m.duration:.1f}s" if m.duration else "unknown"
    sub_str = "subs: yes" if m.has_embedded_subs else "subs: no"

    return [
        f"{title}{year}",
        f"  Path:  {m.path}",
        f"  Video: {res} {codec} | {dur} | {sub_str}",
        "",
    ]


def _format_episode(e: MediaFile) -> list[str]:
    """Format a single episode block."""
    show = e.parsed_title or e.show_key or "(unknown)"
    if e.season and e.episode:
        ep_str = f"S{e.season:02d}E{e.episode:02d}"
    else:
        ep_str = "Unknown"

    res = f"{e.width}x{e.height}" if e.width else "unknown"
    codec = e.codec or "unknown"
    dur = f"{e.duration:.1f}s" if e.duration else "unknown"
    sub_str = "subs: yes" if e.has_embedded_subs else "subs: no"

    return [
        f"{show} {ep_str}",
        f"  Path:  {e.path}",
        f"  Video: {res} {codec} | {dur} | {sub_str}",
        "",
    ]


class TxtReport:
    """Plain text report renderer."""

    def render(self, data: ReportData) -> str:
        """Render the report to a plain text string."""
        lines: list[str] = []

        # Header
        lines.append("MediaVault Report")
        lines.append(f"Scope: {data.scope.value}")
        lines.append("=" * 60)
        lines.append("")

        # Movies
        if data.scope in ("full", "movies"):
            lines.append("== Movies ==")
            if not data.movies:
                lines.append("(none)")
                lines.append("")
            else:
                for m in data.movies:
                    lines.extend(_format_movie(m))
            lines.append("")

        # Episodes
        if data.scope in ("full", "show"):
            lines.append("== Episodes ==")
            if not data.episodes:
                lines.append("(none)")
                lines.append("")
            else:
                for e in data.episodes:
                    lines.extend(_format_episode(e))
            lines.append("")

        # Problems
        lines.append("== Problems ==")
        problems_found = False

        if data.orphan_subtitles:
            problems_found = True
            lines.append("Orphan Subtitles:")
            for p in data.orphan_subtitles:
                lines.append(f"  - {p}")
            lines.append("")

        if data.unparsed_files:
            problems_found = True
            lines.append("Unparsed Files:")
            for f in data.unparsed_files:
                lines.append(f"  - {f.path}")
            lines.append("")

        if data.probe_error_files:
            problems_found = True
            lines.append("Probe Errors:")
            for f in data.probe_error_files:
                lines.append(f"  - {f.path}")
            lines.append("")

        if data.missing_files:
            problems_found = True
            lines.append("Missing Files:")
            for f in data.missing_files:
                lines.append(f"  - {f.path}")
            lines.append("")

        if not problems_found:
            lines.append("(No problems found)")

        lines.append("")

        return "\n".join(lines)

    def write(self, data: ReportData, path: Path) -> None:
        """Render and write to *path* (UTF-8)."""
        path.write_text(self.render(data), encoding="utf-8")
