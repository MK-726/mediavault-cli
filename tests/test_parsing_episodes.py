"""Episode parsing tests (FR-410–FR-418).

Part 2 of Phase 5. Covers directory-wins rules (FR-414, FR-414a),
season-dir validation (FR-415), unparsed-episode fallback (FR-418), and
the apply_parsing dispatch entry point.

apply_parsing contract (assumption 3 = B): returns a NEW list of NEW
MediaFile objects; the caller's list and its elements are untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.parsing import apply_parsing, parse_episode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _episode(name: str, *, parent: Path) -> MediaFile:
    path = parent / name
    suffix = Path(name).suffix.lower()
    return MediaFile(
        path=path,
        filename=name,
        extension=suffix or ".mkv",
        kind=MediaKind.EPISODE,
        size=1,
        mtime_ns=2,
    )


# ---------------------------------------------------------------------------
# FR-410: show key from directory
# ---------------------------------------------------------------------------
def test_show_from_directory_when_only_source(tmp_path):
    show = tmp_path / "Breaking-Bad"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = parse_episode(
        _episode("Breaking.Bad.S01E01.mkv", parent=season), root=tmp_path
    )
    assert mf.show_key == "breaking_bad"
    assert mf.parsed_title == "Breaking Bad"


def test_show_key_punctuation_normalized(tmp_path):
    show = tmp_path / "Spider-Man"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Spider-Man.S01E02.mkv", parent=season), root=tmp_path)
    assert mf.show_key == "spider_man"
    assert mf.parsed_title == "Spider Man"


# ---------------------------------------------------------------------------
# FR-411: season from directory, else filename
# ---------------------------------------------------------------------------
def test_season_from_directory(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-2"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Show.S02E01.mkv", parent=season), root=tmp_path)
    assert mf.season == 2
    assert mf.episode == 1


def test_season_from_filename_when_no_season_dir(tmp_path):
    show = tmp_path / "Chernobyl"
    show.mkdir()
    mf = parse_episode(_episode("Chernobyl.S01E03.mkv", parent=show), root=tmp_path)
    assert mf.season == 1
    assert mf.episode == 3


# ---------------------------------------------------------------------------
# FR-412/FR-413: episode number from filename; pattern tolerance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "filename, want_season, want_episode",
    [
        ("Show.S01E05.mkv", 1, 5),
        ("Show.S1E5.mkv", 1, 5),
        ("Show.S10E12.mkv", 10, 12),
        ("Show.1x05.mkv", 1, 5),
        ("Show.Season.1.Episode.5.mkv", 1, 5),
    ],
)
def test_episode_patterns(tmp_path, filename, want_season, want_episode):
    show = tmp_path / "Show"
    show.mkdir()
    mf = parse_episode(_episode(filename, parent=show), root=tmp_path)
    assert mf.season == want_season
    assert mf.episode == want_episode
    assert mf.parse_status == ParseStatus.OK


# ---------------------------------------------------------------------------
# FR-414: directory wins for show title
# ---------------------------------------------------------------------------
def test_directory_wins_over_filename_for_show(tmp_path):
    show = tmp_path / "Right-Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Wrong.Show.S01E01.mkv", parent=season), root=tmp_path)
    assert mf.parsed_title == "Right Show"
    assert mf.show_key == "right_show"


# ---------------------------------------------------------------------------
# FR-414a: directory wins for season number
# ---------------------------------------------------------------------------
def test_directory_wins_over_filename_for_season(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-2"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Show.S01E03.mkv", parent=season), root=tmp_path)
    assert mf.season == 2
    assert mf.episode == 3


# ---------------------------------------------------------------------------
# FR-415: season-dir validation comes from constants.parse_season_dir
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "season_dir_name, expected_season",
    [
        ("Season-1", 1),
        ("Season-01", 1),
        ("Season-12", 12),
    ],
)
def test_valid_season_dirs_accepted(tmp_path, season_dir_name, expected_season):
    show = tmp_path / "Show"
    season = show / season_dir_name
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Show.S01E01.mkv", parent=season), root=tmp_path)
    assert mf.season == expected_season


def test_invalid_season_dir_treated_as_ordinary(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-001"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Show.S02E05.mkv", parent=season), root=tmp_path)
    assert mf.season == 2
    assert mf.episode == 5


# ---------------------------------------------------------------------------
# FR-416: no episode number but inside Season-* → PARTIAL, episode=NULL
# ---------------------------------------------------------------------------
def test_episode_missing_but_in_season_dir_is_partial(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("extras-featurette.mkv", parent=season), root=tmp_path)
    assert mf.season == 1
    assert mf.episode is None
    assert mf.parse_status == ParseStatus.PARTIAL
    assert mf.parse_confidence == ParseConfidence.LOW


# ---------------------------------------------------------------------------
# FR-418: no episode number AND not inside Season-* → UNPARSED
# ---------------------------------------------------------------------------
def test_unparsed_episode_when_no_pattern_and_no_season_dir(tmp_path):
    show = tmp_path / "Show"
    show.mkdir()
    mf = parse_episode(_episode("random_video.mkv", parent=show), root=tmp_path)
    assert mf.show_key == "show"
    assert mf.season is None
    assert mf.episode is None
    assert mf.parse_status == ParseStatus.UNPARSED


# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------
def test_confidence_high_when_all_components_extracted(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = parse_episode(_episode("Show.S01E01.mkv", parent=season), root=tmp_path)
    assert mf.parse_confidence == ParseConfidence.HIGH


def test_confidence_medium_when_season_from_filename(tmp_path):
    show = tmp_path / "Show"
    show.mkdir()
    mf = parse_episode(_episode("Show.S01E01.mkv", parent=show), root=tmp_path)
    assert mf.parse_confidence == ParseConfidence.MEDIUM


# ---------------------------------------------------------------------------
# FR-404/FR-417: preserve original path/filename; no filesystem access
# ---------------------------------------------------------------------------
def test_preserves_path_and_filename(tmp_path):
    show = tmp_path / "Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = _episode("Show.S01E01.mkv", parent=season)
    original_path, original_name = mf.path, mf.filename
    parse_episode(mf, root=tmp_path)
    assert mf.path == original_path
    assert mf.filename == original_name


def test_does_not_touch_filesystem(tmp_path):
    """Parsing must be filesystem-free (FR-422); file need not exist."""
    show = tmp_path / "Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    mf = _episode("Show.S01E01.mkv", parent=season)
    result = parse_episode(mf, root=tmp_path)
    assert result.parse_status == ParseStatus.OK


# ---------------------------------------------------------------------------
# apply_parsing dispatch
# ---------------------------------------------------------------------------
def test_apply_parsing_dispatches_by_kind(tmp_path):
    movies_root = tmp_path / "movies"
    movies_root.mkdir()

    movie = MediaFile(
        path=movies_root / "Some.Movie.2020.mkv",
        filename="Some.Movie.2020.mkv",
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=2,
    )
    show = movies_root / "Show"
    season = show / "Season-1"
    season.mkdir(parents=True)
    ep = _episode("Show.S01E01.mkv", parent=season)

    result = apply_parsing([movie, ep], root=movies_root)
    assert len(result) == 2
    assert result[0].parsed_title == "Some Movie"
    assert result[0].parsed_year == 2020
    assert result[1].show_key == "show"
    assert result[1].season == 1
    assert result[1].episode == 1
    # assumption 3 = B: originals untouched
    assert movie.parsed_title is None
    assert ep.show_key is None


def test_apply_parsing_returns_new_list_and_new_objects(tmp_path):
    """apply_parsing returns a new list of new MediaFile objects;
    the caller's original list and items are untouched (assumption 3 = B)."""
    original = MediaFile(
        path=tmp_path / "M.2020.mkv",
        filename="M.2020.mkv",
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=2,
    )
    originals = [original]
    result = apply_parsing(originals, root=tmp_path)

    assert result is not originals
    assert result[0] is not original
    assert result[0].parsed_title == "M"
    assert result[0].parsed_year == 2020
    assert original.parsed_title is None
    assert original.parse_status == ParseStatus.UNPARSED
