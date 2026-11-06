"""Filesystem discovery: root-type-agnostic traversal core (FR-310–FR-324).

Part 1 (this file, core):
  * extension / hidden / junk-dir filters
  * symlink policy and cycle detection
  * per-entry error isolation
  * (size, mtime_ns) snapshot at discovery time

Part 2 (dispatchers, appended in the next step):
  * movies / tv / auto classification into MediaFile records
  * DiscoveryResult assembly

This module is UI-agnostic (NFR-015) and stdlib-only apart from
mediavault.constants, mediavault.models, mediavault.logging_setup.
"""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Callable

from mediavault.models import (
    DiscoveryResult,
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
    RootType,
    ScanRoot,
)
from mediavault.constants import (
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    EPISODE_1X02_RE,
    EPISODE_LONG_RE,
    EPISODE_SXXEXX_RE,
    parse_season_dir,
)
from mediavault.logging_setup import get_logger
from mediavault.config.schema import Config


_log = get_logger("discovery")


# ---------------------------------------------------------------------------
# WalkEntry: one filesystem entry observed during traversal
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class WalkEntry:
    """A file or directory observed during traversal.

    ``stat_result`` is captured at observation time so FR-323 can detect
    files modified during the scan (the probe/hash stages compare against
    a later stat).
    """
    path: Path
    is_dir: bool
    size: int | None = None        # None for dirs
    mtime_ns: int | None = None    # None for dirs


# ---------------------------------------------------------------------------
# Filter predicates (pure; no I/O beyond what the caller already did)
# ---------------------------------------------------------------------------
def is_media_file(path: Path) -> bool:
    """FR-311 / FR-315 / FR-316: regular file with a supported video extension.

    Extension matching is case-insensitive. A directory named ``x.mkv`` is
    not a media file (FR-316): callers pass only file entries here, but the
    suffix check makes the intent explicit.
    """
    return path.suffix.lower() in VIDEO_EXTENSIONS and path.is_file()


def is_subtitle_file(path: Path) -> bool:
    """§3.4 / FR-603: a regular file with the supported subtitle extension."""
    return path.suffix.lower() in SUBTITLE_EXTENSIONS and path.is_file()


def matches_any(name: str, patterns: Iterable[str]) -> bool:
    """Case-sensitive fnmatch against a set of glob patterns.

    Used for ``general.skip_dirs`` (FR-319). Matching is intentionally
    case-sensitive: junk-dir names like ``@eaDir`` are case-specific on
    the filesystems they occur on.
    """
    return any(fnmatch.fnmatchcase(name, pat) for pat in patterns)


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class WalkStats:
    """Counters for a single walk. Mutated by ``walk_tree``."""
    dirs_visited: int = 0
    files_visited: int = 0
    errors: int = 0
    symlink_cycles_skipped: int = 0


def walk_tree(
    root: Path,
    *,
    follow_symlinks: bool = False,
    include_hidden: bool = False,
    skip_dirs: Iterable[str] = (),
    prune: Callable[[Path], bool] | None = None,
    stats: WalkStats | None = None,
) -> Iterator[WalkEntry]:
    """Yield WalkEntry for every file and directory under *root*.

    Applies, in order:
      * FR-318: hidden files/dirs skipped unless *include_hidden*
      * FR-319: ``skip_dirs`` patterns skipped (directory basenames)
      * FR-317: symlinks not followed unless *follow_symlinks*
      * FR-324: visited-real-path guard prevents infinite cycles
      * FR-320: unreadable entries logged + counted, walk continues

    Directories are yielded *before* their contents (pre-order), and the
    caller decides which to descend into (or not). If you don't need the
    directories themselves, filter ``entry.is_dir`` out of the stream.

    The generator is lazy: a caller can stop early and the walk stops.

    Parameters
    ----------
    root:
        The directory to walk. The caller is responsible for having
        validated it exists (see ``paths.validate_directory``).
    follow_symlinks:
        If True, symlinked directories are descended. If False, symlinks
        are yielded but not followed.
    include_hidden:
        If True, ``.``-prefixed entries are included. Default False (FR-318).
    skip_dirs:
        Glob patterns matched against directory basenames. Matches are
        skipped and not descended (FR-319).
    stats:
        Optional accumulator for counters. If provided, this function
        mutates it; callers can inspect it after the walk completes.

    Notes
    -----
    Cycle detection uses ``os.path.realpath`` — cheap enough to call once
    per directory on modern systems, and it catches hardlinked bind-mount
    cycles, not just symlink cycles (FR-324).
    """
    if stats is None:
        stats = WalkStats()

    skip_dirs_tuple = tuple(skip_dirs)

    # Maintain a stack of (path, is_symlink_follow) to keep traversal
    # iterative — recursive descent blows the stack on deep trees.
    seen_real_dirs: set[Path] = set()

    stack: list[Path] = [root]
    while stack:
        current = stack.pop()

        # Get a stat for the current entry. ``os.scandir`` is faster but
        # we re-walk lazily here; per-entry stat cost is negligible next
        # to the FFprobe/hash stages and keeps the code readable.
        try:
            st = current.lstat()
        except OSError as exc:
            _log.warning("discovery: cannot stat %s: %s", current, exc)
            stats.errors += 1
            continue

        is_symlink = stat.S_ISLNK(st.st_mode)
        if is_symlink and not follow_symlinks:
            # Yield but do not follow (FR-317).
            yield WalkEntry(path=current, is_dir=False)
            stats.files_visited += 1
            continue

        # Resolve to a real path for the visit-set. ``realpath`` on a
        # nonexistent target returns the unresolved path — that's fine
        # here since we're about to stat it anyway.
        try:
            real = Path(os.path.realpath(current))
        except OSError:
            real = current

        # ------- directory branch -------
        try:
            is_dir = current.is_dir()
        except OSError as exc:
            _log.warning(
                "discovery: cannot check type of %s: %s", current, exc)
            stats.errors += 1
            continue

        if is_dir:
            if real in seen_real_dirs:
                _log.debug("discovery: cycle guard skipping %s", current)
                stats.symlink_cycles_skipped += 1
                continue
            seen_real_dirs.add(real)

            name = current.name
            if not include_hidden and name.startswith(".") and current != root:
                _log.debug("discovery: hidden dir skipped %s", current)
                continue
            if skip_dirs_tuple and matches_any(name, skip_dirs_tuple):
                _log.debug("discovery: junk dir skipped %s", current)
                continue

            stats.dirs_visited += 1

            # don't yield the root itself, only its descendants.
            if current != root:
                yield WalkEntry(path=current, is_dir=True)

            # caller-controlled pruning. If prune(path) returns True, do not
            # descend (but the directory was still yielded above).
            if prune is not None and prune(current):
                _log.debug("discovery: prune requested for %s", current)
                continue

            # Descend. On an unreadable directory, log + continue (FR-320).
            try:
                children = list(current.iterdir())
            except OSError as exc:
                _log.warning("discovery: cannot list %s: %s", current, exc)
                stats.errors += 1
                continue
            # Reverse so the stack pops them in sorted order.
            for child in sorted(children, reverse=True):
                stack.append(child)
            continue

        # ------- file branch -------
        name = current.name
        if not include_hidden and name.startswith("."):
            _log.debug("discovery: hidden file skipped %s", current)
            continue

        stats.files_visited += 1
        yield WalkEntry(
            path=current,
            is_dir=False,
            size=st.st_size,
            mtime_ns=st.st_mtime_ns,
        )


# ---------------------------------------------------------------------------
# Part 2: root-type dispatchers (FR-105, FR-105a, FR-310–FR-314, FR-418)
# ---------------------------------------------------------------------------

_EPISODE_PATTERNS = (EPISODE_SXXEXX_RE, EPISODE_1X02_RE, EPISODE_LONG_RE)


def _looks_like_episode_filename(name: str) -> bool:
    """True if the filename matches any episode pattern (FR-413).

    Used by FR-105a and FR-313/FR-314 for classification, not for parsing.
    Parsing (extracting show/season/episode) happens in Phase 5.
    """
    return any(p.match(name) for p in _EPISODE_PATTERNS)


def _is_season_dir(path: Path) -> bool:
    """True if *path* is a directory whose name is a valid Season-* dir (FR-415)."""
    return path.is_dir() and parse_season_dir(path.name) is not None


def _build_media_file(entry: WalkEntry, kind: MediaKind) -> MediaFile:
    """Construct a MediaFile from a WalkEntry, deferring parsing to Phase 5."""
    return MediaFile(
        path=entry.path,
        filename=entry.path.name,
        extension=entry.path.suffix.lower(),
        kind=kind,
        size=entry.size or 0,
        mtime_ns=entry.mtime_ns or 0,
        parse_status=ParseStatus.UNPARSED,
        parse_confidence=ParseConfidence.LOW,
    )


# ---------------------------------------------------------------------------
# Movies root (FR-310–FR-312)
# ---------------------------------------------------------------------------
def _discover_movies(root: ScanRoot, *, config: Config) -> DiscoveryResult:
    """Recursive movie discovery under a movies root (FR-310).

    FR-312: video files inside a Season-* directory are NOT movies — they
    are skipped (they're a TV construct). We achieve this by pruning any
    Season-* directory during the walk: we still see the directory entry
    (useful for reports/debugging), but we never descend into it, so no
    video files inside it are ever yielded.
    """
    result = DiscoveryResult(root=root)

    def prune(path: Path) -> bool:
        return _is_season_dir(path)

    for entry in walk_tree(
        root.path,
        follow_symlinks=config.general.follow_symlinks,
        include_hidden=config.general.include_hidden,
        skip_dirs=config.general.skip_dirs,
        prune=prune,
    ):
        if entry.is_dir:
            continue
        if not is_media_file(entry.path):
            if is_subtitle_file(entry.path):
                # Orphan subtitles are tracked by Phase 9; skip here.
                pass
            continue
        result.media_files.append(_build_media_file(entry, MediaKind.MOVIE))

    return result


# ---------------------------------------------------------------------------
# TV root (FR-313, FR-314, FR-418)
# ---------------------------------------------------------------------------
def _discover_tv(root: ScanRoot, *, config: Config) -> DiscoveryResult:
    """Show/season/episode discovery under a tv root (FR-313–FR-314).

    Show directories are FIRST-LEVEL subdirectories of the root (FR-313).
    A directory is a show directory if it contains at least one Season-*
    subdirectory OR at least one episode-pattern filename directly.
    Candidates that don't qualify are pruned (no descent).

    Within a show directory (FR-314):
      * under a Season-* directory → episode
      * elsewhere → episode if the filename matches an episode pattern;
        otherwise still an episode with parse_status=UNPARSED (FR-418)
    """
    result = DiscoveryResult(root=root)

    def prune_top_level(path: Path) -> bool:
        # Only prune *direct children* of the root: those are show candidates.
        # Everything deeper is already inside a show and gets fully walked.
        if path.parent != root.path:
            return False
        if not path.is_dir():
            return False
        return not _is_show_directory(path)

    for entry in walk_tree(
        root.path,
        follow_symlinks=config.general.follow_symlinks,
        include_hidden=config.general.include_hidden,
        skip_dirs=config.general.skip_dirs,
        prune=prune_top_level,
    ):
        if entry.is_dir:
            continue
        if not is_media_file(entry.path):
            continue

        in_season_dir = _has_season_ancestor(entry.path, root.path)
        matches_pattern = _looks_like_episode_filename(entry.path.name)

        if in_season_dir or matches_pattern:
            result.media_files.append(
                _build_media_file(entry, MediaKind.EPISODE))
        else:
            # FR-314/FR-418: still an episode, but parsing will fail later.
            result.media_files.append(
                _build_media_file(entry, MediaKind.EPISODE))

    return result


def _is_show_directory(path: Path) -> bool:
    """FR-313: does *path* contain Season-* subdirs or episode-pattern files?"""
    try:
        for child in path.iterdir():
            if child.is_dir() and parse_season_dir(child.name) is not None:
                return True
            if child.is_file() and _looks_like_episode_filename(child.name):
                return True
    except OSError as exc:
        _log.warning(
            "discovery: cannot inspect show candidate %s: %s", path, exc)
        return False
    return False


def _has_season_ancestor(path: Path, stop_at: Path) -> bool:
    """True if some ancestor of *path* (up to *stop_at*) is a Season-* dir."""
    for ancestor in path.parents:
        if ancestor == stop_at:
            return False
        if _is_season_dir(ancestor):
            return True
    return False


# ---------------------------------------------------------------------------
# Auto root (FR-105a)
# ---------------------------------------------------------------------------
def _classify_auto_file(path: Path, root: Path) -> MediaKind:
    """FR-105a: episode if inside Season-* OR filename matches episode pattern.

    Every file gets classified exactly once. Precedence: episode wins.
    """
    if _has_season_ancestor(path, root):
        return MediaKind.EPISODE
    if _looks_like_episode_filename(path.name):
        return MediaKind.EPISODE
    return MediaKind.MOVIE


def _discover_auto(root: ScanRoot, *, config: Config) -> DiscoveryResult:
    """Both passes, per-file precedence (FR-105, FR-105a).

    Unlike movies/tv, an auto root does not prune anything: every file
    must be classified, so every directory must be descended (except the
    usual junk/hidden/season-less rules — auto doesn't know to prune
    Season-* dirs because a Season-* dir under auto might contain movies
    that happen to live in a Season-named folder... but per FR-105a, a file
    inside a Season-* dir is always an episode, so it's safe to still walk.
    """
    result = DiscoveryResult(root=root)

    for entry in walk_tree(
        root.path,
        follow_symlinks=config.general.follow_symlinks,
        include_hidden=config.general.include_hidden,
        skip_dirs=config.general.skip_dirs,
    ):
        if entry.is_dir:
            continue
        if not is_media_file(entry.path):
            continue
        kind = _classify_auto_file(entry.path, root.path)
        _log.debug(
            "discovery: auto root %s classified %s as %s",
            root.path, entry.path, kind.value,
        )
        result.media_files.append(_build_media_file(entry, kind))

    return result


# ---------------------------------------------------------------------------
# Public entry point (FR-105)
# ---------------------------------------------------------------------------
def discover(root: ScanRoot, *, config: Config) -> DiscoveryResult:
    """Dispatch to the correct discovery pass based on ``root.root_type``.

    ``config`` is the resolved application Config (mediavault.config.Config).
    Only ``config.general`` is read here.
    """
    match root.root_type:
        case RootType.MOVIES:
            return _discover_movies(root, config=config)
        case RootType.TV:
            return _discover_tv(root, config=config)
        case RootType.AUTO:
            return _discover_auto(root, config=config)
        case _:  # pragma: no cover - exhaustive above
            raise ValueError(f"unknown root_type: {root.root_type!r}")
