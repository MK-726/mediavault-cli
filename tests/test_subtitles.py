"""Subtitle discovery and matching tests (FR-600–FR-606)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.models import (
    DiscoveryResult,
    MediaFile,
    MediaKind,
    RootType,
    ScanRoot,
    SubtitleKind,
)
from mediavault.subtitles import match_subtitles


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


@pytest.fixture
def mock_discovery(tmp_path) -> DiscoveryResult:
    """Build a fake discovery result with one movie and one show episode."""
    root_path = tmp_path / "media"
    root_path.mkdir()

    # Movie: Movie.Name.2020.mkv
    movie_path = root_path / "Movie.Name.2020.mkv"
    _touch(movie_path)
    movie = MediaFile(
        path=movie_path,
        filename=movie_path.name,
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=2,
    )

    # Episode: Show/Season-1/Show.S01E01.mkv
    ep_path = root_path / "Show" / "Season-1" / "Show.S01E01.mkv"
    _touch(ep_path)
    ep = MediaFile(
        path=ep_path,
        filename=ep_path.name,
        extension=".mkv",
        kind=MediaKind.EPISODE,
        size=1,
        mtime_ns=2,
    )

    root = ScanRoot(path=root_path, root_type=RootType.MOVIES)
    result = DiscoveryResult(root=root)
    result.media_files = [movie, ep]

    return result


# ---------------------------------------------------------------------------
# Basic matching (same directory)
# ---------------------------------------------------------------------------
def test_match_subtitle_same_directory(mock_discovery, tmp_path):
    # Create movie.srt next to movie.mkv
    _touch(tmp_path / "media" / "Movie.Name.2020.srt")

    matches = match_subtitles(mock_discovery)

    assert len(matches) == 1
    media_file, sub = matches[0]

    assert media_file.filename == "Movie.Name.2020.mkv"
    assert sub.kind == SubtitleKind.EXTERNAL
    assert sub.is_primary is True
    assert sub.path == tmp_path / "media" / "Movie.Name.2020.srt"


# ---------------------------------------------------------------------------
# Case insensitivity (FR-603)
# ---------------------------------------------------------------------------
def test_match_subtitle_case_insensitive(mock_discovery, tmp_path):
    _touch(tmp_path / "media" / "movie.name.2020.SRT")

    matches = match_subtitles(mock_discovery)
    assert len(matches) == 1
    assert matches[0][1].path is not None
    assert matches[0][1].path.name == "movie.name.2020.SRT"


# ---------------------------------------------------------------------------
# Subs directory matching (FR-601)
# ---------------------------------------------------------------------------
def test_match_subtitle_subs_directory(mock_discovery, tmp_path):
    # Same-dir subs/
    _touch(tmp_path / "media" / "subs" / "Movie.Name.2020.srt")
    # Ancestor subs/ (season-level)
    _touch(tmp_path / "media" / "Show" / "subs" / "Show.S01E01.srt")

    matches = match_subtitles(mock_discovery)

    assert len(matches) == 2

    for media_file, sub in matches:
        assert sub.kind == SubtitleKind.EXTERNAL
        assert sub.is_primary is True


# ---------------------------------------------------------------------------
# Orphan subtitles (FR-604)
# ---------------------------------------------------------------------------
def test_orphan_subtitles(mock_discovery, tmp_path):
    _touch(tmp_path / "media" / "Orphan.srt")

    result = match_subtitles(mock_discovery, return_orphans=True)

    matches, orphans = result
    assert len(matches) == 0
    assert len(orphans) == 1
    assert orphans[0] == tmp_path / "media" / "Orphan.srt"
