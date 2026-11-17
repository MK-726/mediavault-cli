"""Exact duplicate detection via staged hashing (FR-700–FR-706)."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from mediavault.config.schema import Config
from mediavault.logging_setup import get_logger
from mediavault.models import DuplicateMember, MediaFile

_log = get_logger("duplicates")


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

    for size, candidates in size_groups.items():
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
