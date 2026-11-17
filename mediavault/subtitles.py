"""Subtitle discovery and matching (FR-600–FR-606)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, overload

from mediavault.discovery import is_subtitle_file, walk_tree
from mediavault.models import (
    DiscoveryResult,
    MediaFile,
    Subtitle,
    SubtitleKind,
)


@overload
def match_subtitles(
    discovery_result: DiscoveryResult,
    *,
    return_orphans: Literal[False] = False,
) -> list[tuple[MediaFile, Subtitle]]: ...


@overload
def match_subtitles(
    discovery_result: DiscoveryResult,
    *,
    return_orphans: Literal[True],
) -> tuple[list[tuple[MediaFile, Subtitle]], list[Path]]: ...


def match_subtitles(
    discovery_result: DiscoveryResult,
    *,
    return_orphans: bool = False,
):
    """Find external subtitle files and match them to media files.

    Returns a list of (MediaFile, Subtitle) tuples.
    If return_orphans=True, returns a tuple of (matches, orphan_subtitles).
    """
    root_path = discovery_result.root.path
    media_files = discovery_result.media_files

    # 1. Find all .srt files under the root.
    # We use walk_tree from discovery to respect junk/hidden dirs.
    all_subs: list[Path] = []
    for entry in walk_tree(root_path, include_hidden=False):
        if not entry.is_dir and is_subtitle_file(entry.path):
            all_subs.append(entry.path)

    # Track which subtitles have been matched so we can find orphans.
    matched_subs: set[Path] = set()
    matches: list[tuple[MediaFile, Subtitle]] = []

    # 2. For each media file, search for matching subtitles.
    for mf in media_files:
        mf_stem_lower = mf.path.stem.lower()

        # FR-601: Search order is:
        # 1. Same directory
        # 2. M.parent / "subs"
        # 3. Ancestor A / "subs" up to the root.
        search_dirs: list[Path] = [mf.path.parent]

        # Add parent/subs and ancestor/subs up to root
        current = mf.path.parent
        while True:
            subs_dir = current / "subs"
            if subs_dir not in search_dirs:
                search_dirs.append(subs_dir)
            if current == root_path or current == current.parent:
                break
            current = current.parent

        # Find the best match in the search directories.
        best_match: Path | None = None
        for search_dir in search_dirs:
            # Look for exactly matching stem (case insensitive)
            if not search_dir.exists():
                continue

            candidates = [
                s
                for s in all_subs
                if s.parent == search_dir and s.stem.lower() == mf_stem_lower
            ]

            if candidates:
                # Lexicographic primary if multiple case variants (FR-603)
                candidates.sort(key=lambda p: p.name)
                best_match = candidates[0]
                # Record all matches (FR-602)
                for c in candidates:
                    if c not in matched_subs:
                        matches.append(
                            (
                                mf,
                                Subtitle(
                                    media_file_id=0,
                                    kind=SubtitleKind.EXTERNAL,
                                    path=c,
                                    is_primary=(c == best_match),
                                ),
                            )
                        )
                        matched_subs.add(c)
                break  # We found matches for this media file, stop searching ancestors

    # 3. Find orphans (FR-604)
    orphans = [s for s in all_subs if s not in matched_subs]

    if return_orphans:
        return matches, orphans
    return matches
