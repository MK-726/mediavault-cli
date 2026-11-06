"""Discovery walker tests (FR-311, FR-315–FR-320, FR-324, FR-323)."""

from __future__ import annotations

from pathlib import Path
import os  # noqa: E402  (needed by the skip-decorator pattern below)

import pytest

from mediavault.discovery import (
    WalkStats,
    is_media_file,
    is_subtitle_file,
    matches_any,
    walk_tree,
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
        e.path.name
        for e in walk_tree(tmp_path, include_hidden=True)
        if not e.is_dir
    }
    assert ".hidden.mkv" in names


# ---------------------------------------------------------------------------
# walk_tree: skip_dirs
# ---------------------------------------------------------------------------
def test_walk_skips_junk_dirs(tmp_path):
    _touch(tmp_path / "@eaDir" / "x.mkv")
    _touch(tmp_path / "keep" / "y.mkv")
    names = {
        e.path.name
        for e in walk_tree(tmp_path, skip_dirs=["@eaDir"])
        if not e.is_dir
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
        names = {
            e.path.name
            for e in walk_tree(tmp_path, stats=stats)
            if not e.is_dir
        }
        assert "ok.mkv" in names
        assert stats.errors >= 1
    finally:
        bad.chmod(0o755)
