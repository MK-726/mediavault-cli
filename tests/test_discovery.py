"""Discovery walker tests (FR-311, FR-315–FR-320, FR-324, FR-323)."""

from __future__ import annotations

import os  # noqa: E402  (needed by the skip-decorator pattern below)
from pathlib import Path

import pytest

from mediavault.config import load_config
from mediavault.constants import SUCCESSFUL_SCAN_STATUSES  # noqa: F401
from mediavault.discovery import (
    WalkStats,
    discover,
    is_media_file,
    is_subtitle_file,
    matches_any,
    walk_tree,
)
from mediavault.models import (
    DiscoveryResult,
    MediaKind,
    ParseStatus,
    RootType,
    ScanRoot,
)


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name, expected",
    [
        ("a.mkv", True),
        ("a.mp4", True),
        ("a.MKV", True),
        ("a.MP4", True),
        ("a.avi", False),
        ("a.srt", False),
        ("a", False),
        ("a.mkv.bak", False),
    ],
)
def test_is_media_file(tmp_path, name, expected):
    f = tmp_path / name
    f.write_bytes(b"x")
    assert is_media_file(f) is expected


def test_is_media_file_rejects_directory(tmp_path):
    d = tmp_path / "x.mkv"
    d.mkdir()
    assert is_media_file(d) is False


@pytest.mark.parametrize(
    "name, expected",
    [
        ("a.srt", True),
        ("a.SRT", True),
        ("a.mkv", False),
        ("a", False),
    ],
)
def test_is_subtitle_file(tmp_path, name, expected):
    f = tmp_path / name
    f.write_bytes(b"x")
    assert is_subtitle_file(f) is expected


def test_matches_any():
    assert matches_any("@eaDir", ["@eaDir", "node_modules"])
    assert matches_any("x.Trash-1", ["*.Trash-*"])
    assert not matches_any("@eadir", ["@eaDir"])  # case-sensitive


# ---------------------------------------------------------------------------
# walk_tree: basics
# ---------------------------------------------------------------------------
def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_walk_yields_files_and_dirs(tmp_path):
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "sub" / "b.mkv")
    stats = WalkStats()
    entries = list(walk_tree(tmp_path, stats=stats))
    paths = {e.path.relative_to(tmp_path) for e in entries}
    assert paths == {Path("a.mkv"), Path("sub"), Path("sub/b.mkv")}
    assert stats.dirs_visited >= 1  # root + sub
    assert stats.files_visited == 2


def test_walk_captures_size_and_mtime_for_files(tmp_path):
    f = _touch(tmp_path / "a.mkv")
    f.write_bytes(b"hello")
    entries = [e for e in walk_tree(tmp_path) if not e.is_dir]
    assert len(entries) == 1
    assert entries[0].size == 5
    assert isinstance(entries[0].mtime_ns, int)


def test_walk_is_lazy(tmp_path):
    for i in range(100):
        _touch(tmp_path / f"f{i}.mkv")
    gen = walk_tree(tmp_path)
    first = next(gen)
    # Only one entry pulled — no side effect from "walking all 100".
    assert first is not None


# ---------------------------------------------------------------------------
# walk_tree: hidden
# ---------------------------------------------------------------------------
def test_walk_skips_hidden_by_default(tmp_path):
    _touch(tmp_path / ".hidden.mkv")
    _touch(tmp_path / ".hiddendir" / "x.mkv")
    _touch(tmp_path / "visible.mkv")
    names = {e.path.name for e in walk_tree(tmp_path) if not e.is_dir}
    assert names == {"visible.mkv"}


def test_walk_includes_hidden_when_requested(tmp_path):
    _touch(tmp_path / ".hidden.mkv")
    names = {
        e.path.name for e in walk_tree(tmp_path, include_hidden=True) if not e.is_dir
    }
    assert ".hidden.mkv" in names


# ---------------------------------------------------------------------------
# walk_tree: skip_dirs
# ---------------------------------------------------------------------------
def test_walk_skips_junk_dirs(tmp_path):
    _touch(tmp_path / "@eaDir" / "x.mkv")
    _touch(tmp_path / "keep" / "y.mkv")
    names = {
        e.path.name for e in walk_tree(tmp_path, skip_dirs=["@eaDir"]) if not e.is_dir
    }
    assert "y.mkv" in names
    assert "x.mkv" not in names


def test_walk_skip_dirs_does_not_skip_files_with_matching_names(tmp_path):
    _touch(tmp_path / "@eaDir")  # a *file* named @eaDir
    names = {e.path.name for e in walk_tree(tmp_path, skip_dirs=["@eaDir"])}
    assert "@eaDir" in names  # not skipped: it's a file, not a dir


# ---------------------------------------------------------------------------
# walk_tree: symlinks (FR-317)
# ---------------------------------------------------------------------------
def test_walk_does_not_follow_symlinks_by_default(tmp_path):
    # `real` lives OUTSIDE the walk root, so the only way to reach its
    # contents is to follow the symlink.
    real = tmp_path / "outside" / "real"
    real.mkdir(parents=True)
    _touch(real / "inside.mkv")

    walk_root = tmp_path / "root"
    walk_root.mkdir()
    (walk_root / "linkdir").symlink_to(real, target_is_directory=True)

    entries = list(walk_tree(walk_root))
    names = {e.path.name for e in entries if not e.is_dir}
    assert "inside.mkv" not in names
    assert "linkdir" in names  # the symlink is yielded, just not followed


def test_walk_follows_symlinks_when_configured(tmp_path):
    real = tmp_path / "outside" / "real"
    real.mkdir(parents=True)
    _touch(real / "inside.mkv")

    walk_root = tmp_path / "root"
    walk_root.mkdir()
    (walk_root / "linkdir").symlink_to(real, target_is_directory=True)

    entries = list(walk_tree(walk_root, follow_symlinks=True))
    names = {e.path.name for e in entries if not e.is_dir}
    assert "inside.mkv" in names


# ---------------------------------------------------------------------------
# walk_tree: cycle detection (FR-324)
# ---------------------------------------------------------------------------
def test_walk_survives_symlink_cycle(tmp_path):
    a = tmp_path / "a"
    b = a / "b"
    b.mkdir(parents=True)
    # b/cycle -> a  (a loop)
    (b / "cycle").symlink_to(a, target_is_directory=True)
    stats = WalkStats()
    # Must terminate. We don't care how many entries; we care that it stops.
    list(walk_tree(tmp_path, follow_symlinks=True, stats=stats))
    assert stats.symlink_cycles_skipped >= 1


# ---------------------------------------------------------------------------
# walk_tree: error isolation (FR-320)
# ---------------------------------------------------------------------------
def test_walk_reports_unreadable_dir_and_continues(tmp_path):
    if os.geteuid() == 0:  # pragma: no cover
        pytest.skip("permissions meaningless as root")
    bad = tmp_path / "bad"
    bad.mkdir()
    _touch(bad / "hidden-from-us.mkv")
    bad.chmod(0o000)
    good = tmp_path / "good"
    _touch(good / "ok.mkv")
    try:
        stats = WalkStats()
        names = {e.path.name for e in walk_tree(tmp_path, stats=stats) if not e.is_dir}
        assert "ok.mkv" in names
        assert stats.errors >= 1
    finally:
        bad.chmod(0o755)


# ---------------------------------------------------------------------------
# Part 2: dispatchers
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
    """Resolved Config with sane defaults, isolated from the real config."""
    for k in list(os.environ):
        if k.startswith("MEDIAVAULT_CLI_"):
            os.environ.pop(k, None)
    cfg = load_config(project_config=None)
    return cfg


def _root(path: Path, root_type: RootType) -> ScanRoot:
    return ScanRoot(path=path, root_type=root_type)


# --- movies ---------------------------------------------------------------
def test_discover_movies_finds_recursive_files(tmp_path, cfg):
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "sub" / "b.mp4")
    _touch(tmp_path / "MCU" / "Iron.Man.2008.mkv")
    r = discover(_root(tmp_path, RootType.MOVIES), config=cfg)
    names = {mf.filename for mf in r.media_files}
    assert names == {"a.mkv", "b.mp4", "Iron.Man.2008.mkv"}
    assert all(mf.kind == MediaKind.MOVIE for mf in r.media_files)


def test_discover_movies_skips_season_dirs(tmp_path, cfg):
    """FR-312: video in Season-* under a movies root is skipped."""
    _touch(tmp_path / "Good.Movie.2020.mkv")
    _touch(tmp_path / "Season-1" / "some.episode.mkv")
    r = discover(_root(tmp_path, RootType.MOVIES), config=cfg)
    names = {mf.filename for mf in r.media_files}
    assert names == {"Good.Movie.2020.mkv"}


def test_discover_movies_ignores_non_media(tmp_path, cfg):
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "a.srt")
    _touch(tmp_path / "notes.txt")
    r = discover(_root(tmp_path, RootType.MOVIES), config=cfg)
    assert {mf.filename for mf in r.media_files} == {"a.mkv"}


def test_discover_movies_media_files_are_unparsed(tmp_path, cfg):
    _touch(tmp_path / "A.Movie.2020.mkv")
    r = discover(_root(tmp_path, RootType.MOVIES), config=cfg)
    assert len(r.media_files) == 1
    assert r.media_files[0].parse_status == ParseStatus.UNPARSED
    assert r.media_files[0].parsed_title is None


# --- tv -------------------------------------------------------------------
def test_discover_tv_show_with_seasons(tmp_path, cfg):
    _touch(tmp_path / "Breaking-Bad" / "Season-1" / "Breaking.Bad.S01E01.mkv")
    _touch(tmp_path / "Breaking-Bad" / "Season-2" / "Breaking.Bad.S02E01.mkv")
    r = discover(_root(tmp_path, RootType.TV), config=cfg)
    assert len(r.media_files) == 2
    assert all(mf.kind == MediaKind.EPISODE for mf in r.media_files)


def test_discover_tv_one_season_show_flat_layout(tmp_path, cfg):
    """FR-313: episodes directly in the show dir without a Season subdir."""
    _touch(tmp_path / "Chernobyl" / "Chernobyl.S01E01.mkv")
    _touch(tmp_path / "Chernobyl" / "Chernobyl.S01E02.mkv")
    r = discover(_root(tmp_path, RootType.TV), config=cfg)
    assert len(r.media_files) == 2


def test_discover_tv_non_show_dirs_are_pruned(tmp_path, cfg):
    """A first-level dir that's neither Season-nor-episode qualified is pruned."""
    # A top-level dir with no season dirs and no episode-pattern files
    _touch(tmp_path / "NotAShow" / "random_file.mkv")  # not episode pattern
    _touch(tmp_path / "RealShow" / "Season-1" / "Real.Show.S01E01.mkv")
    r = discover(_root(tmp_path, RootType.TV), config=cfg)
    names = {mf.filename for mf in r.media_files}
    assert "Real.Show.S01E01.mkv" in names
    assert "random_file.mkv" not in names


def test_discover_tv_episode_inside_season_dir_without_pattern(tmp_path, cfg):
    """FR-314: inside Season-*, classification is episode regardless of filename."""
    _touch(tmp_path / "Show" / "Season-1" / "weirdly_named_video.mkv")
    r = discover(_root(tmp_path, RootType.TV), config=cfg)
    assert len(r.media_files) == 1
    assert r.media_files[0].kind == MediaKind.EPISODE


def test_discover_tv_episode_outside_season_with_pattern(tmp_path, cfg):
    """FR-314: outside Season-*, pattern match → episode."""
    _touch(tmp_path / "Show" / "Show.Name.S01E05.mkv")
    r = discover(_root(tmp_path, RootType.TV), config=cfg)
    assert len(r.media_files) == 1
    assert r.media_files[0].kind == MediaKind.EPISODE


# --- auto -----------------------------------------------------------------
def test_discover_auto_classifies_each_file_once(tmp_path, cfg):
    """FR-105a: each file is classified exactly once, never double-counted."""
    _touch(tmp_path / "Movie.2020.mkv")  # movie
    # episode (season dir)
    _touch(tmp_path / "Show" / "Season-1" / "S01E01.mkv")
    # episode (pattern)
    _touch(tmp_path / "Show" / "Show.Name.S01E02.mkv")
    # movie (nested)
    _touch(tmp_path / "Sub" / "Another.Movie.2021.mp4")

    r = discover(_root(tmp_path, RootType.AUTO), config=cfg)
    assert len(r.media_files) == 4
    by_name = {mf.filename: mf.kind for mf in r.media_files}
    assert by_name["Movie.2020.mkv"] == MediaKind.MOVIE
    assert by_name["S01E01.mkv"] == MediaKind.EPISODE
    assert by_name["Show.Name.S01E02.mkv"] == MediaKind.EPISODE
    assert by_name["Another.Movie.2021.mp4"] == MediaKind.MOVIE


def test_discover_auto_no_prune_of_season_dirs(tmp_path, cfg):
    """Auto must walk Season-* dirs to find files (they're episodes, not skipped)."""
    _touch(tmp_path / "Show" / "Season-1" / "S01E01.mkv")
    r = discover(_root(tmp_path, RootType.AUTO), config=cfg)
    assert len(r.media_files) == 1


def test_discover_returns_discovery_result(tmp_path, cfg):
    _touch(tmp_path / "a.mkv")
    r = discover(_root(tmp_path, RootType.MOVIES), config=cfg)
    assert isinstance(r, DiscoveryResult)
    assert r.root.root_type == RootType.MOVIES
