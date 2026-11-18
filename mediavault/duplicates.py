"""Exact duplicate detection via staged hashing (FR-700–FR-706)."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from mediavault.config.schema import Config
from mediavault.logging_setup import get_logger
from mediavault.models import (
    DuplicateMember,
    MediaFile,
    MediaKind,
    NearDuplicateGroup,
    NearDuplicateMember,
)
from mediavault.parsing import to_match_key

_log = get_logger("duplicates")


def _require_id(mf: MediaFile) -> int:
    """Return mf.id, asserting it is set. Used to narrow types for Pyright."""
    if mf.id is None:
        raise ValueError(f"MediaFile {mf.path} has no id")
    return mf.id


def _hash_file_partial(path: Path, bytes_to_read: int) -> str:
    """Compute a SHA-256 hash of the first and last `bytes_to_read` bytes."""
    hasher = hashlib.sha256()
    file_size = path.stat().st_size

    with path.open("rb") as f:
        # Read start
        hasher.update(f.read(bytes_to_read))

        # Read end (if file is large enough to not overlap)
        if file_size > bytes_to_read * 2:
            f.seek(-bytes_to_read, 2)  # Seek from end
            hasher.update(f.read(bytes_to_read))
        elif file_size > bytes_to_read:
            # If it's between 1x and 2x the partial size, read the rest
            f.seek(bytes_to_read)
            hasher.update(f.read())

    return hasher.hexdigest()


def _hash_file_full(path: Path, chunk_size: int) -> str:
    """Compute a full SHA-256 hash of the file in chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_exact_duplicates(
    media_files: list[MediaFile],
    config: Config,
) -> list[list[DuplicateMember]]:
    """Find byte-identical files using staged hashing (FR-701).

    Returns a list of groups, where each group is a list of DuplicateMembers
    that share the exact same full SHA-256 hash.
    """
    # Filter out files that don't have an ID yet (shouldn't happen in scan).
    valid_files = [mf for mf in media_files if mf.id is not None]

    # 1. Group by size (FR-701 step 1)
    size_groups: dict[int, list[MediaFile]] = defaultdict(list)
    for mf in valid_files:
        size_groups[mf.size].append(mf)

    duplicate_groups: list[list[DuplicateMember]] = []

    for _, candidates in size_groups.items():
        if len(candidates) < 2:
            continue  # Unique size, cannot be a duplicate

        # 2. Partial hash (FR-701 step 2)
        partial_bytes = config.duplicates.partial_hash_bytes
        partial_groups: dict[str, list[MediaFile]] = defaultdict(list)

        for mf in candidates:
            try:
                p_hash = _hash_file_partial(mf.path, partial_bytes)
                partial_groups[p_hash].append(mf)
            except OSError as exc:
                _log.warning("duplicates: failed to partial-hash %s: %s", mf.path, exc)
                continue

        # 3. Full hash (FR-701 step 3)
        chunk_bytes = config.duplicates.hash_chunk_bytes

        for p_hash, p_candidates in partial_groups.items():
            if len(p_candidates) < 2:
                continue  # Unique partial hash

            full_groups: dict[str, list[MediaFile]] = defaultdict(list)
            for mf in p_candidates:
                try:
                    f_hash = _hash_file_full(mf.path, chunk_bytes)
                    full_groups[f_hash].append(mf)
                except OSError as exc:
                    _log.warning("duplicates: failed to full-hash %s: %s", mf.path, exc)
                    continue

            # 4. Assemble duplicate groups
            for f_hash, f_candidates in full_groups.items():
                if len(f_candidates) > 1:
                    members = []
                    for mf in f_candidates:
                        assert mf.id is not None
                        members.append(
                            DuplicateMember(
                                group_id=0, media_file_id=mf.id, hash_value=f_hash
                            )
                        )
                    duplicate_groups.append(members)

    return duplicate_groups


def _near_dup_key(mf: MediaFile) -> tuple | None:
    """Compute the similarity key for a MediaFile (FR-710).

    Returns None when the file cannot participate in near-dup grouping
    (missing required components).
    """
    if mf.kind == MediaKind.MOVIE:
        if mf.parsed_title is None or mf.parsed_year is None:
            return None
        return (to_match_key(mf.parsed_title), mf.parsed_year)
    else:  # episode
        if mf.show_key is None or mf.season is None or mf.episode is None:
            return None
        return (mf.show_key, mf.season, mf.episode)


def find_near_duplicates(
    media_files: list[MediaFile],
    exact_groups: list[list[DuplicateMember]],
) -> list[NearDuplicateGroup]:
    """Group files by similarity key where ≥2 distinct hashes exist (FR-710–FR-714).

    Parameters
    ----------
    media_files:
        The files to consider (typically from the current scan).
    exact_groups:
        The exact-duplicate groups from ``find_exact_duplicates``. Used to
        look up each file's hash and to annotate exact-duplicate siblings.
    """
    # Build a map from media_file_id -> hash_value using the exact groups.
    hash_by_id: dict[int, str] = {}
    for group in exact_groups:
        for member in group:
            if member.hash_value is not None:
                hash_by_id[member.media_file_id] = member.hash_value

    # Group files by their similarity key.
    by_key: dict[tuple, list[MediaFile]] = {}
    for mf in media_files:
        _require_id(mf)
        key = _near_dup_key(mf)
        if key is None:
            continue
        by_key.setdefault(key, []).append(mf)

    results: list[NearDuplicateGroup] = []

    for key, candidates in by_key.items():
        if len(candidates) < 2:
            continue

        # FR-711: group requires ≥2 distinct hashes.
        # Hash is only known for files that were in an exact group; files
        # without a hash (i.e. size-unique or partial-hash-unique) are
        # treated as having an implicit "unknown but distinct" hash — BUT
        # the SRS says "≥2 distinct content hashes exist within that key".
        # In practice every file the scanner cares about has been hashed if
        # it had a size collision. Files without hashes cannot be proven
        # to be exact dups, so they count as distinct.
        hashes: set[str] = set()
        for mf in candidates:
            h = hash_by_id.get(_require_id(mf))
            if h is not None:
                hashes.add(h)
            else:
                # No hash means the file was unique on its own; treat as
                # an implicit distinct hash so it can still form a group.
                hashes.add(f"__unknown_{_require_id(mf)}__")

        if len(hashes) < 2:
            continue  # All candidates are exact copies of each other

        # Build members. A member is an "exact dup of sibling" iff another
        # member in the same group shares its hash.
        hash_counts: dict[str, int] = {}
        for mf in candidates:
            h = hash_by_id.get(_require_id(mf))
            if h is not None:
                hash_counts[h] = hash_counts.get(h, 0) + 1

        members = []
        for mf in candidates:
            mid = _require_id(mf)
            h = hash_by_id.get(_require_id(mf))
            is_exact = h is not None and hash_counts.get(h, 0) > 1
            members.append(
                NearDuplicateMember(
                    media_file_id=mid,
                    hash_value=h,
                    is_exact_dup_of_sibling=is_exact,
                )
            )

        results.append(NearDuplicateGroup(key=key, members=tuple(members)))

    return results
