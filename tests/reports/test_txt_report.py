"""TXT report tests (FR-1102, FR-1103, FR-1104)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.reports.base import ReportData, ReportScope
from mediavault.reports.txt import TxtReport


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
    has_external_subs: bool = False,
    dup_group: int | None = None,
    parse_status: ParseStatus = ParseStatus.OK,
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
        parse_status=parse_status,
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
    movies = [
        _movie("/lib/a.mkv", title="A Movie", year=2020, mf_id=1),
        _movie(
            "/lib/b.mkv",
            title="B Movie",
            year=2021,
            codec="hevc",
            width=3840,
            height=2160,
            mf_id=2,
        ),
    ]
    episodes = [
        _episode(
            "/lib/S/Season-1/S.S01E01.mkv", show="Show", season=1, episode=1, mf_id=3
        ),
        _episode(
            "/lib/S/Season-1/S.S01E02.mkv", show="Show", season=1, episode=2, mf_id=4
        ),
    ]
    return ReportData(
        scope=ReportScope.FULL,
        movies=tuple(movies),
        episodes=tuple(episodes),
        orphan_subtitles=(),
        unparsed_files=(),
        probe_error_files=(),
        missing_files=(),
        movies_without_external_subs=(),
    )


# ---------------------------------------------------------------------------
# Header + sections
# ---------------------------------------------------------------------------
def test_txt_report_has_header(data):
    out = TxtReport().render(data)
    assert "MediaVault Report" in out
    assert "Scope: full" in out


def test_txt_report_movies_section(data):
    out = TxtReport().render(data)
    assert "== Movies ==" in out
    assert "A Movie (2020)" in out
    assert "B Movie (2021)" in out


def test_txt_report_episodes_section(data):
    out = TxtReport().render(data)
    assert "== Episodes ==" in out
    assert "Show S01E01" in out
    assert "Show S01E02" in out


def test_txt_report_problems_section_always_present(data):
    out = TxtReport().render(data)
    assert "== Problems ==" in out


def test_txt_report_no_problems_when_clean(data):
    out = TxtReport().render(data)
    assert "(No problems found)" in out


def test_txt_subs_label_variants():
    """Hybrid subs label: ext / emb / both / none (FR-1102/1103)."""
    movies = [
        _movie("/lib/a.mkv", title="A", year=2020, mf_id=1),  # none
        _movie(
            "/lib/b.mkv", title="B", year=2020, mf_id=2, has_embedded_subs=True
        ),  # emb
        _movie("/lib/c.mkv", title="C", year=2020, mf_id=3),  # ext
        _movie(
            "/lib/d.mkv", title="D", year=2020, mf_id=4, has_embedded_subs=True
        ),  # both
    ]
    data = ReportData(
        scope=ReportScope.MOVIES,
        movies=tuple(movies),
        episodes=(),
        files_with_external_subs=frozenset({3, 4}),
    )
    out = TxtReport().render(data)
    assert "A (2020)" in out and "subs: none" in out
    assert "B (2020)" in out and "subs: emb" in out
    assert "C (2020)" in out and "subs: ext" in out
    assert "D (2020)" in out and "subs: both" in out


# ---------------------------------------------------------------------------
# Problem sections (FR-1104)
# ---------------------------------------------------------------------------


def test_txt_orphan_subtitles(data):
    from dataclasses import replace

    data = replace(data, orphan_subtitles=(Path("/lib/orphan.srt"),))
    out = TxtReport().render(data)
    assert "Orphan Subtitles:" in out
    assert "- /lib/orphan.srt" in out


def test_txt_unparsed_files(data):
    from dataclasses import replace

    bad = _movie(
        "/lib/bad.mkv",
        title="bad",
        year=None,
        parse_status=ParseStatus.UNPARSED,
        mf_id=99,
    )
    data = replace(data, unparsed_files=(bad,))
    out = TxtReport().render(data)
    assert "Unparsed Files:" in out
    assert "- /lib/bad.mkv" in out


def test_txt_probe_errors(data):
    from dataclasses import replace

    bad = _movie(
        "/lib/broken.mkv", title="Broken", year=2020, codec="", mf_id=99
    )  # codec empty = not probed
    data = replace(data, probe_error_files=(bad,))
    out = TxtReport().render(data)
    assert "Probe Errors:" in out
    assert "- /lib/broken.mkv" in out


def test_txt_missing_files(data):
    from dataclasses import replace

    missing = _movie("/lib/gone.mkv", title="Gone", year=2020, mf_id=99)
    data = replace(data, missing_files=(missing,))
    out = TxtReport().render(data)
    assert "Missing Files:" in out
    assert "- /lib/gone.mkv" in out


def test_txt_all_problems_together(data):
    from dataclasses import replace

    data = replace(
        data,
        orphan_subtitles=(Path("/lib/o.srt"),),
        unparsed_files=(
            _movie(
                "/lib/u.mkv",
                title="u",
                year=None,
                parse_status=ParseStatus.UNPARSED,
                mf_id=90,
            ),
        ),
        probe_error_files=(_movie("/lib/p.mkv", title="p", year=2020, mf_id=91),),
        missing_files=(_movie("/lib/m.mkv", title="m", year=2020, mf_id=92),),
    )
    out = TxtReport().render(data)
    for heading in (
        "Orphan Subtitles:",
        "Unparsed Files:",
        "Probe Errors:",
        "Missing Files:",
    ):
        assert heading in out


# ---------------------------------------------------------------------------
# Scope filtering (FR-1101)
# ---------------------------------------------------------------------------
def test_txt_scope_movies_only(data):
    from dataclasses import replace

    data = replace(data, scope=ReportScope.MOVIES)
    out = TxtReport().render(data)
    assert "== Movies ==" in out
    assert "== Episodes ==" not in out


def test_txt_scope_show_only(data):
    from dataclasses import replace

    data = replace(data, scope=ReportScope.SHOW)
    out = TxtReport().render(data)
    assert "== Movies ==" not in out
    assert "== Episodes ==" in out
