"""Scan orchestration (FR-102, FR-102a, FR-103, FR-806, FR-807)."""

from __future__ import annotations

from mediavault.config.schema import Config
from mediavault.database.repository import Repository
from mediavault.discovery import discover
from mediavault.logging_setup import get_logger
from mediavault.models import (
    MediaKind,
    ScanRoot,
    ScanRun,
    ScanStatus,
)
from mediavault.parsing import apply_parsing
from mediavault.paths import is_root_mounted

_log = get_logger("services.scanner")


def scan_roots(
    repo: Repository,
    roots: list[ScanRoot],
    *,
    config: Config,
) -> ScanRun:
    """Execute a scan across the given roots and persist the results.

    Implements the scan lifecycle:
      1. Start a scan run (FR-102).
      2. For each root, discover media files (FR-105).
      3. Parse the discovered files (FR-400–FR-422).
      4. Persist files and record scan membership (FR-102a).
      5. Mark files from previous scans as missing if they weren't seen
         this time (FR-806), skipping this for unmounted roots (FR-322).
      6. Finalize the scan run with counters and status.
    """
    # 1. Start the scan
    scan = repo.start_scan()

    # Assert to satisfy the type checker and enforce the invariant.
    assert scan.id is not None

    _log.info("scanner: started scan %d across %d root(s)", scan.id, len(roots))

    filesystem_errors = 0
    movies_found = 0
    episodes_found = 0
    distinct_shows: set[str] = set()

    # Keep track of all media file IDs seen in this scan for missing-marking.
    seen_media_ids: set[int] = set()
    # Track roots that were successfully scanned (mounted) for FR-322.
    scanned_root_ids: set[int] = set()

    for root in roots:
        if root.id is None:
            raise ValueError("ScanRoot must have an ID before scanning")

        # FR-322: Check if the root is currently accessible.
        if not is_root_mounted(root.path):
            _log.warning("scanner: root is unmounted or missing: %s", root.path)
            filesystem_errors += 1
            continue  # Skip discovery and missing-marking for this root

        scanned_root_ids.add(root.id)

        # 2. Discovery
        _log.debug("scanner: discovering %s", root.path)
        discovery_result = discover(root, config=config)

        # Merge walk errors into the filesystem error count.
        # (discover() aggregates these in DiscoveryResult)
        filesystem_errors += (
            len(discovery_result.errors) if hasattr(discovery_result, "errors") else 0
        )

        if not discovery_result.media_files:
            _log.debug("scanner: no media files found in %s", root.path)
            continue

        # 3. Parsing (returns new MediaFile objects; originals untouched)
        parsed_files = apply_parsing(discovery_result.media_files, root=root.path)

        # 4. Persistence
        for mf in parsed_files:
            # Try to find an existing record for this path.
            existing = repo.get_media_file_by_path(mf.path)

            if existing is not None:
                # Update existing record
                mf.id = existing.id
                mf.last_seen_scan_id = scan.id
                mf.missing_since_scan_id = None  # FR-807: clear missing status
                repo.update_media_file(mf)
                media_id = mf.id
            else:
                # Insert new record
                mf.last_seen_scan_id = scan.id
                saved = repo.insert_media_file(mf)
                media_id = saved.id

            # Assert to narrow int | None -> int for Pyright
            assert media_id is not None

            # Track this file as seen (FR-806)
            seen_media_ids.add(media_id)

            # FR-102a: Record historical scan membership
            repo.record_scan_membership(scan.id, media_id)

            # Tally counters
            if mf.kind == MediaKind.MOVIE:
                movies_found += 1
            else:
                episodes_found += 1
                if mf.show_key:
                    distinct_shows.add(mf.show_key)

    # 5. Missing-file detection (FR-806)
    # Only check files whose roots were successfully scanned (FR-322).
    if scanned_root_ids:
        # We need to find files that were last seen in a previous scan,
        # belong to one of the scanned roots, and weren't seen this time.
        for root_id in scanned_root_ids:
            root_path = next(r.path for r in roots if r.id == root_id)

            # Query DB for active files under this root path prefix.
            # (Using LIKE prefix because we stored absolute paths.)
            rows = repo.conn.execute(
                """
                SELECT id, path FROM media_files
                WHERE path LIKE ? AND missing_since_scan_id IS NULL
                """,
                (f"{root_path}%",),
            ).fetchall()

            for row in rows:
                file_id = row["id"]
                # If we didn't see it this scan, mark it missing.
                if file_id not in seen_media_ids:
                    repo.mark_missing(file_id, scan.id)
                    _log.debug("scanner: marked missing: %s", row["path"])

    # 6. Finalize the scan
    status = ScanStatus.PARTIAL if filesystem_errors > 0 else ScanStatus.COMPLETED
    finished_scan = repo.finish_scan(
        scan.id,
        status=status,
        movies_found=movies_found,
        shows_found=len(distinct_shows),
        episodes_found=episodes_found,
        filesystem_errors=filesystem_errors,
    )

    # FR-103/FR-809: Record the last successful scan ID.
    if finished_scan.status in (ScanStatus.COMPLETED, ScanStatus.PARTIAL):
        repo.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("last_successful_scan_id", str(finished_scan.id)),
        )
        repo.conn.commit()

    _log.info(
        "scanner: finished scan %d with status %s "
        "(movies=%d, shows=%d, episodes=%d, errors=%d)",
        finished_scan.id,
        finished_scan.status.value,
        finished_scan.movies_found,
        finished_scan.shows_found,
        finished_scan.episodes_found,
        finished_scan.errors_count,
    )

    return finished_scan
