"""Markdown report tests (FR-1102, FR-1103, FR-1104, FR-1107)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.reports.base import ReportData, ReportScope
from mediavault.reports.markdown import MarkdownReport


def _movie(
    path: str,
    *,
    title: str,
    year: int | None,
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    duration: float = 120.0,
    has_embedded_subs: bool = False,
    mf_id: int = 1,
) -> MediaFile:
    return MediaFile(
        path=Path(path),
        filename=Path(path).name,
        extension=Path(path).suffix.lower(),
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=1,
        id=mf_id,
        parsed_title=title,
        parsed_year=year,
        parse_status=ParseStatus.OK,
        parse_confidence=ParseConfidence.HIGH,
        codec=codec,
        width=width,
        height=height,
        duration=duration,
        has_embedded_subs=has_embedded_subs,
    )


def _episode(
    path: str,
    *,
    show: str,
    season: int,
    episode: int,
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    duration: float = 45.0,
    has_embedded_subs: bool = False,
    mf_id: int = 1,
) -> MediaFile:
    return MediaFile(
        path=Path(path),
        filename=Path(path).name,
        extension=Path(path).suffix.lower(),
        kind=MediaKind.EPISODE,
        size=1,
        mtime_ns=1,
        id=mf_id,
        parsed_title=show,
        show_key=show.lower().replace(" ", "_"),
        season=season,
        episode=episode,
        parse_status=ParseStatus.OK,
        parse_confidence=ParseConfidence.HIGH,
        codec=codec,
        width=width,
        height=height,
        duration=duration,
        has_embedded_subs=has_embedded_subs,
    )


@pytest.fixture
def data() -> ReportData:
    return ReportData(
        scope=ReportScope.FULL,
        generated_at="2025-01-01T12:00:00Z",
        movies=(
            _movie("/lib/a.mkv", title="A Movie", year=2020, mf_id=1),
            _movie(
                "/lib/b.mkv",
                title="B Movie",
                year=2021,
                codec="hevc",
                width=3840,
                height=2160,
                mf_id=2,
                has_embedded_subs=True,
            ),
        ),
        episodes=(
            _episode(
                "/lib/S/Season-1/S.S01E01.mkv",
                show="Show",
                season=1,
                episode=1,
                mf_id=3,
            ),
        ),
        files_with_external_subs=frozenset({2, 3}),
    )


# ---------------------------------------------------------------------------
# Title, metadata block, counts
# ---------------------------------------------------------------------------
def test_md_has_title_and_metadata(data):
    out = MarkdownReport().render(data)
    assert "## MediaVault Report" in out
    assert "**Scope:** full" in out
    assert "**Generated:** 2025-01-01T12:00:00Z" in out
    # Counts
    assert "Movies: 2" in out
    assert "Episodes: 1" in out


def test_md_omits_generated_when_empty(data):
    data = replace(data, generated_at="")
    out = MarkdownReport().render(data)
    assert "**Generated:**" not in out


# ---------------------------------------------------------------------------
# Movies table
# ---------------------------------------------------------------------------
def test_md_movies_table_headers(data):
    out = MarkdownReport().render(data)
    assert "### Movies" in out
    assert "| Title | Year | Resolution | Codec | Duration | Ext | Emb | Path |" in out
    assert "| --- | --- | --- | --- | --- | --- | --- | --- |" in out


def test_md_movies_row_values(data):
    out = MarkdownReport().render(data)
    # Row for A Movie: no subs at all
    assert "| A Movie | 2020 | 1920x1080 | h264 | 120.0s | ✗ | ✗ | /lib/a.mkv |" in out
    # Row for B Movie: both
    assert "| B Movie | 2021 | 3840x2160 | hevc | 120.0s | ✓ | ✓ | /lib/b.mkv |" in out


# ---------------------------------------------------------------------------
# Episodes table
# ---------------------------------------------------------------------------
def test_md_episodes_table_headers(data):
    out = MarkdownReport().render(data)
    assert "### Episodes" in out
    assert (
        "| Show | Season | Episode | Resolution | Codec | Duration "
        "| Ext | Emb | Path |" in out
    )


def test_md_episodes_row_values(data):
    out = MarkdownReport().render(data)
    # S01E01 has external subs only
    assert (
        "| Show | 1 | 1 | 1920x1080 | h264 | 45.0s | ✓ | ✗ "
        "| /lib/S/Season-1/S.S01E01.mkv |" in out
    )


# ---------------------------------------------------------------------------
# Problems section
# ---------------------------------------------------------------------------
def test_md_problems_subsections(data):
    data = replace(
        data,
        orphan_subtitles=(Path("/lib/orphan.srt"),),
        unparsed_files=(_movie("/lib/u.mkv", title="u", year=None, mf_id=90),),
        probe_error_files=(_movie("/lib/p.mkv", title="p", year=2020, mf_id=91),),
        missing_files=(_movie("/lib/m.mkv", title="m", year=2020, mf_id=92),),
    )
    out = MarkdownReport().render(data)
    assert "### Problems" in out
    assert "#### Orphan Subtitles" in out
    assert "- `/lib/orphan.srt`" in out
    assert "#### Unparsed Files" in out
    assert "- `/lib/u.mkv`" in out
    assert "#### Probe Errors" in out
    assert "- `/lib/p.mkv`" in out
    assert "#### Missing Files" in out
    assert "- `/lib/m.mkv`" in out


def test_md_no_problems_shows_note(data):
    out = MarkdownReport().render(data)
    assert "_No problems found._" in out
    assert "#### Orphan Subtitles" not in out


# ---------------------------------------------------------------------------
# Scope filtering
# ---------------------------------------------------------------------------
def test_md_scope_movies_only(data):
    data = replace(data, scope=ReportScope.MOVIES)
    out = MarkdownReport().render(data)
    assert "### Movies" in out
    assert "### Episodes" not in out


def test_md_scope_show_only(data):
    data = replace(data, scope=ReportScope.SHOW)
    out = MarkdownReport().render(data)
    assert "### Movies" not in out
    assert "### Episodes" in out


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------
def test_md_write_to_file(data, tmp_path):
    path = tmp_path / "report.md"
    MarkdownReport().write(data, path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "## MediaVault Report" in content
