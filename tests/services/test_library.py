"""Library service tests (FR-900–FR-905)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.services.library import (
    browse_episodes,
    browse_movies,
    browse_shows,
    search,
)


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    repo = Repository(conn)
    yield repo
    conn.close()


@pytest.fixture
def seeded(repo):
    """Populate the DB with a small mixed library."""
    scan = repo.start_scan()

    def add(path: str, **kwargs) -> MediaFile:
        mf = MediaFile(
            path=Path(path),
            filename=Path(path).name,
            extension=Path(path).suffix.lower(),
            kind=kwargs.pop("kind", MediaKind.MOVIE),
            size=100,
            mtime_ns=1,
            parse_status=kwargs.pop("parse_status", ParseStatus.OK),
            parse_confidence=kwargs.pop("parse_confidence", ParseConfidence.HIGH),
            **kwargs,
        )
        return repo.insert_media_file(mf)

    # Movies
    add(
        "/lib/a.mkv",
        parsed_title="A Movie",
        parsed_year=2020,
        codec="h264",
        width=1920,
        height=1080,
        duration=120.0,
        has_embedded_subs=True,
    )
    add(
        "/lib/b.mkv",
        parsed_title="B Movie",
        parsed_year=2021,
        codec="hevc",
        width=3840,
        height=2160,
        duration=90.0,
        has_embedded_subs=False,
    )
    add(
        "/lib/c.mkv",
        parsed_title="C Movie",
        parsed_year=2022,
        codec="h264",
        width=1280,
        height=720,
        duration=60.0,
        has_embedded_subs=False,
        missing_since_scan_id=scan.id,
    )  # missing

    # Episodes
    e1 = add(
        "/lib/Show/Season-1/Show.S01E01.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=1,
        episode=1,
        parsed_title="Show",
        codec="h264",
        width=1920,
        height=1080,
        duration=45.0,
        has_embedded_subs=True,
    )
    add(
        "/lib/Show/Season-1/Show.S01E02.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=1,
        episode=2,
        parsed_title="Show",
        codec="h264",
        width=1920,
        height=1080,
        duration=45.0,
        has_embedded_subs=False,
    )
    add(
        "/lib/Show/Season-2/Show.S02E01.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=2,
        episode=1,
        parsed_title="Show",
        codec="hevc",
        width=1920,
        height=1080,
        duration=45.0,
        has_embedded_subs=False,
    )

    # External subtitle on e1
    repo.conn.execute(
        "INSERT INTO subtitles (media_file_id, path, kind, is_primary) "
        "VALUES (?, ?, 'external', 1)",
        (e1.id, "/lib/Show/Season-1/Show.S01E01.srt"),
    )
    repo.conn.commit()

    return repo


# ---------------------------------------------------------------------------
# Browse movies (FR-900)
# ---------------------------------------------------------------------------
def test_browse_movies_excludes_missing(seeded):
    rows, total = browse_movies(seeded)
    assert total == 2
    assert {m.parsed_title for m in rows} == {"A Movie", "B Movie"}


def test_browse_movies_include_missing(seeded):
    rows, total = browse_movies(seeded, include_missing=True)
    assert total == 3


# ---------------------------------------------------------------------------
# Browse shows (FR-901)
# ---------------------------------------------------------------------------
def test_browse_shows_counts(seeded):
    rows, total = browse_shows(seeded)
    assert total == 1
    show = rows[0]
    assert show.show_key == "show"
    assert show.episode_count == 3
    assert show.season_count == 2


# ---------------------------------------------------------------------------
# Browse episodes (FR-902)
# ---------------------------------------------------------------------------
def test_browse_episodes_all(seeded):
    rows, total = browse_episodes(seeded, show_key="show")
    assert total == 3


def test_browse_episodes_by_season(seeded):
    rows, total = browse_episodes(seeded, show_key="show", season=1)
    assert total == 2


# ---------------------------------------------------------------------------
# Search (FR-903)
# ---------------------------------------------------------------------------
def test_search_by_title(seeded):
    rows, total = search(seeded, title="A Movie")
    assert total == 1
    assert rows[0].parsed_title == "A Movie"


def test_search_by_year(seeded):
    rows, total = search(seeded, year=2021)
    assert total == 1
    assert rows[0].parsed_year == 2021


def test_search_by_codec(seeded):
    rows, total = search(seeded, codec="hevc")
    assert total == 2  # B movie + S02E01


def test_search_by_resolution(seeded):
    rows, total = search(seeded, resolution="3840x2160")
    assert total == 1
    assert rows[0].parsed_title == "B Movie"


def test_search_by_duration_range(seeded):
    rows, total = search(seeded, min_duration=50, max_duration=100)
    # B movie (90), C movie (60, but missing — excluded by default)
    # Episodes: all 45s — below min_duration
    assert total == 1
    assert rows[0].parsed_title == "B Movie"


# ---------------------------------------------------------------------------
# Subtitle filter semantics (FR-903)
# ---------------------------------------------------------------------------
def test_search_has_subs_or(seeded):
    """--has-subs = external OR embedded."""
    rows, total = search(seeded, has_subs=True)
    # A movie (embedded), S01E01 (embedded + external)
    assert total == 2


def test_search_has_external_subs(seeded):
    rows, total = search(seeded, has_external_subs=True)
    assert total == 1
    assert rows[0].episode == 1


def test_search_has_embedded_subs(seeded):
    rows, total = search(seeded, has_embedded_subs=True)
    # A movie + S01E01
    assert total == 2


def test_search_no_subs(seeded):
    rows, total = search(seeded, has_subs=False)
    # B movie (not missing), S01E02, S02E01
    assert total == 3


# ---------------------------------------------------------------------------
# Conflicting filters (FR-903a)
# ---------------------------------------------------------------------------
def test_search_rejects_has_subs_and_no_subs(seeded):
    with pytest.raises(UsageError):
        search(seeded, has_subs=True, no_subs=True)


def test_search_rejects_external_and_no_subs(seeded):
    with pytest.raises(UsageError):
        search(seeded, has_external_subs=True, no_subs=True)


def test_search_rejects_embedded_and_no_subs(seeded):
    with pytest.raises(UsageError):
        search(seeded, has_embedded_subs=True, no_subs=True)


# ---------------------------------------------------------------------------
# Pagination (FR-905)
# ---------------------------------------------------------------------------
def test_search_pagination(seeded):
    page1, total = search(seeded, limit=2, offset=0)
    assert total == 5  # A, B (movies), plus 3 episodes
    assert len(page1) == 2

    page2, total2 = search(seeded, limit=2, offset=2)
    assert total2 == 5
    assert len(page2) == 2
    assert {m.id for m in page1}.isdisjoint({m.id for m in page2})
