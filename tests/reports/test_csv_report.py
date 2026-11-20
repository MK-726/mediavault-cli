"""CSV report tests (FR-1102, FR-1103, FR-1104, FR-1105, FR-1106)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.reports.base import ReportData, ReportScope
from mediavault.reports.csv_report import CsvReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
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


def _parse(text: str) -> list[dict[str, str]]:
    """Parse a single-section CSV string into list of dicts."""
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------
def test_csv_movies_header(data):
    text = CsvReport().render_movies(data)
    rows = _parse(text)
    assert "title" in rows[0]
    assert "year" in rows[0]
    assert "resolution" in rows[0]
    assert "codec" in rows[0]
    assert "duration_s" in rows[0]
    assert "has_external_subs" in rows[0]
    assert "has_embedded_subs" in rows[0]
    assert "duplicate_group" in rows[0]
    assert "path" in rows[0]


def test_csv_movie_values(data):
    rows = _parse(CsvReport().render_movies(data))
    a = next(r for r in rows if r["title"] == "A Movie")
    assert a["year"] == "2020"
    assert a["resolution"] == "1920x1080"
    assert a["codec"] == "h264"
    assert a["has_external_subs"] == "false"
    assert a["has_embedded_subs"] == "false"
    assert a["path"] == "/lib/a.mkv"

    b = next(r for r in rows if r["title"] == "B Movie")
    assert b["has_external_subs"] == "true"
    assert b["has_embedded_subs"] == "true"


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------
def test_csv_episodes_header_and_values(data):
    rows = _parse(CsvReport().render_episodes(data))
    assert "show" in rows[0]
    assert "season" in rows[0]
    assert "episode" in rows[0]
    e = rows[0]
    assert e["show"] == "Show"
    assert e["season"] == "1"
    assert e["episode"] == "1"
    assert e["has_external_subs"] == "true"
    assert e["has_embedded_subs"] == "false"


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------
def test_csv_problems_section(data):
    from dataclasses import replace

    data = replace(
        data,
        orphan_subtitles=(Path("/lib/orphan.srt"),),
        unparsed_files=(_movie("/lib/u.mkv", title="u", year=None, mf_id=90),),
        probe_error_files=(_movie("/lib/p.mkv", title="p", year=2020, mf_id=91),),
        missing_files=(_movie("/lib/m.mkv", title="m", year=2020, mf_id=92),),
    )
    text = CsvReport().render_problems(data)
    rows = _parse(text)
    assert len(rows) == 4
    kinds = {r["kind"] for r in rows}
    assert kinds == {"orphan_subtitle", "unparsed", "probe_error", "missing"}
    paths = {r["path"] for r in rows}
    assert "/lib/orphan.srt" in paths
    assert "/lib/u.mkv" in paths
    assert "/lib/p.mkv" in paths
    assert "/lib/m.mkv" in paths


def test_csv_problems_empty(data):
    """When there are no problems, render header only."""
    text = CsvReport().render_problems(data)
    rows = _parse(text)
    assert rows == []


# ---------------------------------------------------------------------------
# RFC 4180 quoting (FR-1106)
# ---------------------------------------------------------------------------
def test_csv_quoting_special_chars():
    movie = _movie("/lib/weird,name.mkv", title='A "Quoted" Title', year=2020, mf_id=1)
    data = ReportData(
        scope=ReportScope.MOVIES,
        movies=(movie,),
        episodes=(),
    )
    text = CsvReport().render_movies(data)
    assert '"A ""Quoted"" Title"' in text


# ---------------------------------------------------------------------------
# write() → multiple files
# ---------------------------------------------------------------------------
def test_csv_write_produces_three_files(data, tmp_path):
    base = tmp_path / "full-20250101"
    written = CsvReport().write(data, base)
    names = sorted(p.name for p in written)
    assert names == [
        "full-20250101-episodes.csv",
        "full-20250101-movies.csv",
        "full-20250101-problems.csv",
    ]
    for p in written:
        assert p.exists()
        assert p.stat().st_size > 0


def test_csv_write_scope_movies_only(tmp_path):
    data = ReportData(
        scope=ReportScope.MOVIES,
        movies=(_movie("/lib/a.mkv", title="A", year=2020, mf_id=1),),
        episodes=(),
    )
    written = CsvReport().write(data, tmp_path / "movies-20250101")
    names = sorted(p.name for p in written)
    # No episodes file for MOVIES scope
    assert names == [
        "movies-20250101-movies.csv",
        "movies-20250101-problems.csv",
    ]
