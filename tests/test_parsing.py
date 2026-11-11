"""Parsing tests: normalization + movie parsing (FR-400–FR-422)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.parsing import (
    parse_movie,
    strip_junk_tokens,
    to_display_title,
    to_match_key,
)


def _movie(name: str) -> MediaFile:
    suffix = Path(name).suffix.lower()
    return MediaFile(
        path=Path("/x") / name,
        filename=name,
        # Discovery sets extension from suffix; for the adversarial
        # "...mkv" case the suffix is "" but the file is conceptually
        # a .mkv. Fall back to .mkv so the helper matches what the test
        # intends to exercise.
        extension=suffix or ".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=2,
    )


# ---------------------------------------------------------------------------
# to_display_title (FR-402)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("A.Clockwork.Orange", "A Clockwork Orange"),
        ("A Clockwork Orange", "A Clockwork Orange"),
        ("Spider-Man", "Spider Man"),
        ("Spider_Man", "Spider Man"),
        ("Schindler's List", "Schindlers List"),
        ("Schindler’s List", "Schindlers List"),  # curly apostrophe
        ("Ocean's 11", "Oceans 11"),
        ("10.Cloverfield.Lane", "10 Cloverfield Lane"),
        ("Amélie", "Amélie"),
        ("The.Matrix", "The Matrix"),
        ("MCU", "Mcu"),  # no acronym preservation
        ("  extra   spaces  ", "Extra Spaces"),
        ("", ""),
        ("...", ""),
    ],
)
def test_to_display_title(raw, expected):
    assert to_display_title(raw) == expected


# ---------------------------------------------------------------------------
# to_match_key (FR-402)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("A.Clockwork.Orange", "a_clockwork_orange"),
        ("Schindler's List", "schindlers_list"),
        ("Spider-Man", "spider_man"),
        ("10.Cloverfield.Lane", "10_cloverfield_lane"),
        ("Amélie", "amélie"),
        ("", ""),
    ],
)
def test_to_match_key(raw, expected):
    assert to_match_key(raw) == expected


# ---------------------------------------------------------------------------
# strip_junk_tokens (FR-401)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Movie.2020.1080p.BluRay.x264", "Movie 2020"),
        ("Movie 2020 1080p", "Movie 2020"),
        ("1080p.Movie.2020", "Movie 2020"),
        ("WEB-DL.Movie", "Movie"),  # hyphenated junk token — FIXED
        ("Movie.Extended.Cut", "Movie"),
        ("NoJunkHere", "NoJunkHere"),
        ("Spider-Man", "Spider Man"),  # title hyphen survives
        ("Movie.H.264.1080p", "Movie"),
        ("", ""),
    ],
)
def test_strip_junk_tokens(raw, expected):
    assert strip_junk_tokens(raw) == expected


# ---------------------------------------------------------------------------
# parse_movie — the four FR-400 patterns
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "filename, want_title, want_year, want_status, want_conf",
    [
        # Pattern 1: Title (Year) [junk].ext
        (
            "A Clockwork Orange (1971) [1080p].mkv",
            "A Clockwork Orange",
            1971,
            ParseStatus.OK,
            ParseConfidence.HIGH,
        ),
        ("Movie (2020).mkv", "Movie", 2020, ParseStatus.OK, ParseConfidence.MEDIUM),
        # Pattern 2: Title.Year.Resolution.Source.Codec
        (
            "A.Clockwork.Orange.1971.1080p.BluRay.x264.mkv",
            "A Clockwork Orange",
            1971,
            ParseStatus.OK,
            ParseConfidence.HIGH,
        ),
        # Pattern 3: Title.Year.Resolution
        (
            "A.Clockwork.Orange.1971.1080p.mkv",
            "A Clockwork Orange",
            1971,
            ParseStatus.OK,
            ParseConfidence.HIGH,
        ),
        # Pattern 4: Title.Year
        (
            "A.Clockwork.Orange.1971.mkv",
            "A Clockwork Orange",
            1971,
            ParseStatus.OK,
            ParseConfidence.HIGH,
        ),
        # Underscore form
        (
            "Spider_Man_2002.mkv",
            "Spider Man",
            2002,
            ParseStatus.OK,
            ParseConfidence.HIGH,
        ),
    ],
)
def test_parse_movie_ok_patterns(
    filename, want_title, want_year, want_status, want_conf
):
    mf = parse_movie(_movie(filename))
    assert mf.parsed_title == want_title
    assert mf.parsed_year == want_year
    assert mf.parse_status == want_status
    assert mf.parse_confidence == want_conf


def test_parse_movie_partial_no_year():
    """FR-421: title present but no year → PARTIAL."""
    mf = parse_movie(_movie("Some.Movie.Without.Year.mkv"))
    assert mf.parsed_title == "Some Movie Without Year"
    assert mf.parsed_year is None
    assert mf.parse_status == ParseStatus.PARTIAL
    assert mf.parse_confidence == ParseConfidence.LOW


def test_parse_movie_unparsed_on_empty():
    mf = parse_movie(_movie("...mkv"))  # stem is empty after stripping
    assert mf.parse_status == ParseStatus.UNPARSED
    assert mf.parsed_title is None


def test_parse_movie_preserves_path_and_filename():
    """FR-404: original filename and path always preserved."""
    mf = _movie("Garbage.@@@.mkv")
    original_path, original_name = mf.path, mf.filename
    parse_movie(mf)
    assert mf.path == original_path
    assert mf.filename == original_name


def test_parse_movie_no_year_in_title_leaks():
    """FR-402: year must not appear inside parsed_title."""
    mf = parse_movie(_movie("A.Clockwork.Orange.1971.1080p.mkv"))
    assert mf.parsed_title is not None
    assert "1971" not in mf.parsed_title
    assert "1080p" not in mf.parsed_title


def test_parse_movie_year_in_title_before_actual_year():
    """A title ending in a 4-digit number shouldn't be mistaken for a year
    unless it's the LAST meaningful token before junk."""
    mf = parse_movie(_movie("Blade.Runner.2049.2017.1080p.mkv"))
    # 2049 is part of the title; 2017 is the year.
    assert mf.parsed_year == 2017
    assert mf.parsed_title is not None
    assert "2049" in mf.parsed_title  # 2049 stays; 2017 is the year
