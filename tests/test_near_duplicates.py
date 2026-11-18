"""Near-duplicate detection tests (FR-710–FR-714)."""

from __future__ import annotations

from pathlib import Path

from mediavault.duplicates import find_near_duplicates
from mediavault.models import (
    DuplicateMember,
    MediaFile,
    MediaKind,
    ParseStatus,
)


def _mf(
    name: str,
    *,
    title: str | None = None,
    year: int | None = None,
    show_key: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    kind: MediaKind = MediaKind.MOVIE,
    mf_id: int,
) -> MediaFile:
    return MediaFile(
        path=Path("/x") / name,
        filename=name,
        extension=".mkv",
        kind=kind,
        size=100,
        mtime_ns=1,
        id=mf_id,
        parsed_title=title,
        parsed_year=year,
        show_key=show_key,
        season=season,
        episode=episode,
        parse_status=ParseStatus.OK,
    )


# ---------------------------------------------------------------------------
# Movies: near-dup by (title, year)
# ---------------------------------------------------------------------------
def test_near_dup_movies_different_resolutions():
    """Two files with same title+year but different hashes → near-dup group."""
    mf1 = _mf("A.Movie.2020.1080p.mkv", title="A Movie", year=2020, mf_id=1)
    mf2 = _mf("A.Movie.2020.2160p.mkv", title="A Movie", year=2020, mf_id=2)

    # Different hashes (not exact dups)
    exact_groups = [
        [DuplicateMember(group_id=1, media_file_id=1, hash_value="hash1")],
        [DuplicateMember(group_id=2, media_file_id=2, hash_value="hash2")],
    ]

    near = find_near_duplicates([mf1, mf2], exact_groups)
    assert len(near) == 1
    g = near[0]
    assert g.key == ("a_movie", 2020)
    assert len(g.members) == 2
    assert all(m.is_exact_dup_of_sibling is False for m in g.members)


def test_near_dup_movies_same_key_but_one_exact_dup():
    """Three files: two are exact dups, one is different → all in near group."""
    mf1 = _mf("A.Movie.2020.1080p.mkv", title="A Movie", year=2020, mf_id=1)
    mf2 = _mf("A.Movie.2020.1080p.b.mkv", title="A Movie", year=2020, mf_id=2)
    mf3 = _mf("A.Movie.2020.2160p.mkv", title="A Movie", year=2020, mf_id=3)

    # 1 and 2 are exact dups, 3 is different
    exact_groups = [
        [
            DuplicateMember(group_id=1, media_file_id=1, hash_value="hash1"),
            DuplicateMember(group_id=1, media_file_id=2, hash_value="hash1"),
        ],
        [DuplicateMember(group_id=2, media_file_id=3, hash_value="hash3")],
    ]

    near = find_near_duplicates([mf1, mf2, mf3], exact_groups)
    assert len(near) == 1
    assert len(near[0].members) == 3
    # 1 and 2 should be marked as exact copies
    by_id = {m.media_file_id: m for m in near[0].members}
    assert by_id[1].is_exact_dup_of_sibling is True
    assert by_id[2].is_exact_dup_of_sibling is True
    assert by_id[3].is_exact_dup_of_sibling is False


def test_no_near_dup_if_only_one_file():
    mf = _mf("A.Movie.2020.mkv", title="A Movie", year=2020, mf_id=1)
    near = find_near_duplicates([mf], [])
    assert near == []


def test_no_near_dup_if_different_years():
    mf1 = _mf("A.Movie.2020.mkv", title="A Movie", year=2020, mf_id=1)
    mf2 = _mf("A.Movie.2021.mkv", title="A Movie", year=2021, mf_id=2)
    near = find_near_duplicates([mf1, mf2], [])
    assert near == []


def test_no_near_dup_if_missing_year():
    """FR-710: files without a year are excluded from near-dup."""
    mf1 = _mf("A.Movie.mkv", title="A Movie", year=None, mf_id=1)
    mf2 = _mf("A.Movie.b.mkv", title="A Movie", year=None, mf_id=2)
    near = find_near_duplicates([mf1, mf2], [])
    assert near == []


# ---------------------------------------------------------------------------
# Episodes: near-dup by (show_key, season, episode)
# ---------------------------------------------------------------------------
def test_near_dup_episodes():
    mf1 = _mf(
        "Show.S01E01.1080p.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=1,
        episode=1,
        mf_id=1,
    )
    mf2 = _mf(
        "Show.S01E01.720p.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=1,
        episode=1,
        mf_id=2,
    )
    near = find_near_duplicates([mf1, mf2], [])
    assert len(near) == 1
    assert near[0].key == ("show", 1, 1)
    assert len(near[0].members) == 2


def test_no_near_dup_episode_missing_season():
    mf1 = _mf(
        "Show.S01E01.1080p.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=None,
        episode=1,
        mf_id=1,
    )
    mf2 = _mf(
        "Show.S01E01.720p.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=None,
        episode=1,
        mf_id=2,
    )
    near = find_near_duplicates([mf1, mf2], [])
    assert near == []


# ---------------------------------------------------------------------------
# FR-711: group requires ≥2 distinct hashes
# ---------------------------------------------------------------------------
def test_no_near_dup_when_all_exact():
    """All files are exact copies of each other → not a 'near' group."""
    mf1 = _mf("A.Movie.2020.a.mkv", title="A Movie", year=2020, mf_id=1)
    mf2 = _mf("A.Movie.2020.b.mkv", title="A Movie", year=2020, mf_id=2)
    exact_groups = [
        [
            DuplicateMember(group_id=1, media_file_id=1, hash_value="samehash"),
            DuplicateMember(group_id=1, media_file_id=2, hash_value="samehash"),
        ],
    ]
    near = find_near_duplicates([mf1, mf2], exact_groups)
    assert near == []
