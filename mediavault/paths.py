"""Path validation and canonicalization (FR-300–FR-304, FR-321, FR-322, FR-1110).

All path handling goes through pathlib (NFR-007). This module is
stdlib-only and has no MediaVault imports except the error type — it
satisfies the import-boundary rule (NFR-015).
"""

from __future__ import annotations

import os
from pathlib import Path

from mediavault.errors import PathValidationError


# ---------------------------------------------------------------------------
# Basic validation (FR-300–FR-304)
# ---------------------------------------------------------------------------
def expand_path(path: str | os.PathLike[str]) -> Path:
    """Expand ``~`` and return an absolute Path, without resolving symlinks.

    Does not touch the filesystem; safe to call on nonexistent paths.
    """
    return Path(path).expanduser().absolute()


def validate_directory(path: str | os.PathLike[str]) -> Path:
    """Validate that *path* refers to a directory and return its resolved form.

    Implements FR-300–FR-303:
      * path must exist
      * symlinks are resolved and re-validated
      * a regular file (or a symlink that resolves to one) is rejected

    Raises
    ------
    PathValidationError
        With a user-facing message explaining which check failed.
    """
    p = expand_path(path)

    if not p.exists():
        raise PathValidationError(f"path does not exist: {p}")

    # Resolve symlinks so subsequent checks are against the real target.
    resolved = p.resolve()

    if not resolved.is_dir():
        raise PathValidationError(f"not a directory: {p}")

    return resolved


def validate_path(path: str | os.PathLike[str]) -> Path:
    """Validate that *path* exists (file or directory) and return its resolved form.

    Used for places that accept either (e.g. a config file path).
    Raises PathValidationError if the path does not exist.
    """
    p = expand_path(path)
    if not p.exists():
        raise PathValidationError(f"path does not exist: {p}")
    return p.resolve()


# ---------------------------------------------------------------------------
# Root canonicalization and overlap removal (FR-321)
# ---------------------------------------------------------------------------
def canonicalize_and_dedupe_roots(roots: list[Path]) -> list[Path]:
    """Resolve and de-duplicate scan roots; drop descendants of ancestors.

    Implements FR-321:
      * Resolve every root.
      * If one root is an ancestor of another, keep the ancestor only.
      * Preserve first-seen order; duplicates collapse.
      * A media file is never recorded twice in one scan as a result.

    Returns a new list; the input is not modified.
    """
    resolved: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        r = root.resolve()
        if r in seen:
            continue
        seen.add(r)
        resolved.append(r)

    # Drop any root that is a descendant of another root in the list.
    kept: list[Path] = []
    for r in resolved:
        if any(r != other and other in r.parents for other in resolved):
            continue
        kept.append(r)
    return kept


# ---------------------------------------------------------------------------
# Mountedness (FR-322)
# ---------------------------------------------------------------------------
def is_root_mounted(root: Path) -> bool:
    """Return True if *root* is currently accessible on the filesystem.

    FR-322 needs to distinguish "no media files in a mounted empty dir"
    (legitimate) from "root's mount point is missing" (the external drive
    is unplugged) — the latter must skip missing-file marking for that root.

    A path is considered mounted iff it exists AND is a directory. This
    errs toward treating unavailable roots as unmounted, which is the safe
    direction per FR-322 (never mark files missing under an unmounted root).
    """
    try:
        return root.exists() and root.is_dir()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Containment check (FR-1110)
# ---------------------------------------------------------------------------
def is_inside_scan_root(path: Path, scan_roots: list[Path]) -> bool:
    """Return True if *path* resolves to *inside* any scan root.

    Used by FR-1110 to reject report output dirs inside a scan root, which
    protects the read-only scan-root guarantee (NFR-002).

    A path is "inside" a root if it is equal to the root or a descendant
    of it. Both sides are resolved before comparison so symlinked roots and
    ``..`` tricks don't bypass the check.
    """
    p = path.resolve()
    for root in scan_roots:
        r = root.resolve()
        if p == r or r in p.parents:
            return True
    return False
