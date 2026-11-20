"""Markdown report formatter (FR-1102–FR-1104, FR-1107)."""

from __future__ import annotations

from pathlib import Path

from mediavault.reports.base import ReportData


def _check(b: bool | None) -> str:
    return "✓" if b else "✗"


def _resolution(w: int | None, h: int | None) -> str:
    return f"{w}x{h}" if w and h else "unknown"


def _duration(d: float | None) -> str:
    return f"{d:.1f}s" if d else "unknown"


class MarkdownReport:
    """Markdown report renderer."""

    def render(self, data: ReportData) -> str:
        lines: list[str] = []

        # Title + metadata block
        lines.append("## MediaVault Report")
        lines.append("")
        lines.append(f"**Scope:** {data.scope.value}")
        if data.generated_at:
            lines.append(f"**Generated:** {data.generated_at}")
        lines.append("")
        lines.append(f"Movies: {len(data.movies)}")
        lines.append(f"Episodes: {len(data.episodes)}")
        lines.append("")

        ext_ids = data.files_with_external_subs

        # Movies section
        if data.scope in ("full", "movies"):
            lines.append("### Movies")
            lines.append("")
            lines.append(
                "| Title | Year | Resolution | Codec | Duration | Ext | Emb | Path |"
            )
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            if not data.movies:
                lines.append("| _(none)_ | | | | | | | |")
            else:
                for m in data.movies:
                    has_ext = m.id in ext_ids
                    lines.append(
                        f"| {m.parsed_title or '(untitled)'} "
                        f"| {m.parsed_year or ''} "
                        f"| {_resolution(m.width, m.height)} "
                        f"| {m.codec or 'unknown'} "
                        f"| {_duration(m.duration)} "
                        f"| {_check(has_ext)} "
                        f"| {_check(bool(m.has_embedded_subs))} "
                        f"| {m.path} |"
                    )
            lines.append("")

        # Episodes section
        if data.scope in ("full", "show"):
            lines.append("### Episodes")
            lines.append("")
            lines.append(
                "| Show | Season | Episode | Resolution | Codec | Duration "
                "| Ext | Emb | Path |"
            )
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            if not data.episodes:
                lines.append("| _(none)_ | | | | | | | | |")
            else:
                for e in data.episodes:
                    has_ext = e.id in ext_ids
                    show = e.parsed_title or e.show_key or "(unknown)"
                    season = e.season if e.season is not None else ""
                    episode = e.episode if e.episode is not None else ""
                    lines.append(
                        f"| {show} "
                        f"| {season} "
                        f"| {episode} "
                        f"| {_resolution(e.width, e.height)} "
                        f"| {e.codec or 'unknown'} "
                        f"| {_duration(e.duration)} "
                        f"| {_check(has_ext)} "
                        f"| {_check(bool(e.has_embedded_subs))} "
                        f"| {e.path} |"
                    )
            lines.append("")

        # Problems section
        lines.append("### Problems")
        lines.append("")

        problem_sections = [
            ("Orphan Subtitles", [f"- `{p}`" for p in data.orphan_subtitles]),
            ("Unparsed Files", [f"- `{f.path}`" for f in data.unparsed_files]),
            ("Probe Errors", [f"- `{f.path}`" for f in data.probe_error_files]),
            ("Missing Files", [f"- `{f.path}`" for f in data.missing_files]),
        ]

        # Filter to non-empty sections
        non_empty = [(h, items) for h, items in problem_sections if items]

        if not non_empty:
            lines.append("_No problems found._")
        else:
            for heading, items in non_empty:
                lines.append(f"#### {heading}")
                lines.append("")
                lines.extend(items)
                lines.append("")

        return "\n".join(lines)

    def write(self, data: ReportData, path: Path) -> None:
        """Render and write to *path* (UTF-8)."""
        path.write_text(self.render(data), encoding="utf-8")
