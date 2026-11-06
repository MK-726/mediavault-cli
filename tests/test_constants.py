"""Constants module tests, focused on the non-obvious pieces (FR-415, FR-413)."""

from __future__ import annotations

import pytest

from mediavault.constants import (
    EPISODE_1X02_RE,
    EPISODE_LONG_RE,
    EPISODE_SXXEXX_RE,
    VIDEO_EXTENSIONS,
    parse_season_dir,
)


@pytest.mark.parametrize(
    "name, expected",
    [
        # 1-9 permissive
        ("Season-1", 1),
        ("Season-01", 1),
        ("Season-9", 9),
        ("Season-09", 9),
        ("season-5", 5),  # case-insensitive
        # >=10 unpadded only
        ("Season-10", 10),
        ("Season-12", 12),
        ("Season-100", 100),
        # rejected (FR-415)
        ("Season-0", None),
        ("Season-00", None),
        ("Season-001", None),
        ("Season-010", None),
        ("Season-", None),
        ("Season1", None),
        ("Season_1", None),
        ("season-1-extra", None),
        ("NotASeason", None),
    ],
)
def test_parse_season_dir(name, expected):
    assert parse_season_dir(name) == expected


@pytest.mark.parametrize(
    "pattern, filename, expected",
    [
        (EPISODE_SXXEXX_RE, "Breaking.Bad.S01E02.1080p.mkv",
         {"show": "Breaking.Bad", "season": "01", "episode": "02"}),
        (EPISODE_SXXEXX_RE, "Chernobyl.S01E01.mkv",
         {"show": "Chernobyl", "season": "01", "episode": "01"}),
        (EPISODE_SXXEXX_RE, "Show.Name.S1E2.mkv",
         {"show": "Show.Name", "season": "1", "episode": "2"}),
        (EPISODE_1X02_RE, "Breaking.Bad.1x02.720p.mkv",
         {"show": "Breaking.Bad", "season": "1", "episode": "02"}),
        (EPISODE_LONG_RE, "Breaking.Bad.Season.1.Episode.2.mkv",
         {"show": "Breaking.Bad", "season": "1", "episode": "2"}),
    ],
)
def test_episode_patterns_match(pattern, filename, expected):
    m = pattern.match(filename)
    assert m is not None, f"{pattern.pattern!r} did not match {filename!r}"
    for key, value in expected.items():
        assert m.group(key) == value


@pytest.mark.parametrize(
    "pattern, filename",
    [
        (EPISODE_SXXEXX_RE, "Breaking.Bad.1080p.mkv"),
        (EPISODE_SXXEXX_RE, "Breaking.Bad.S01.mkv"),
        (EPISODE_1X02_RE, "Breaking.Bad.S01E02.mkv"),
    ],
)
def test_episode_patterns_reject(pattern, filename):
    assert pattern.match(filename) is None


def test_video_extensions():
    assert VIDEO_EXTENSIONS == frozenset({".mkv", ".mp4"})
