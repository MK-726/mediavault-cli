"""Data-access layer (FR-804)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
    RootType,
    ScanRoot,
    ScanRun,
    ScanStatus,
)


class Repository:
    """All SQL access is mediated through this class (FR-804)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -----------------------------------------------------------------------
    # Scan Roots
    # -----------------------------------------------------------------------
    def insert_scan_root(self, root: ScanRoot) -> ScanRoot:
        cur = self.conn.execute(
            "INSERT INTO scan_roots (path, root_type) VALUES (?, ?)",
            (str(root.path), root.root_type.value),
        )
        self.conn.commit()

        # Assert to narrow int | None -> int for the type checker.
        assert cur.lastrowid is not None
        return self.get_scan_root(cur.lastrowid)

    def get_scan_root(self, root_id: int) -> ScanRoot:
        row = self.conn.execute(
            "SELECT * FROM scan_roots WHERE id = ?", (root_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Scan root {root_id} not found")

        return ScanRoot(
            id=row["id"],
            path=Path(row["path"]),
            root_type=RootType(row["root_type"]),
            added_at=row["added_at"],
            last_scan_id=row["last_scan_id"],
        )

    def list_scan_roots(self) -> list[ScanRoot]:
        rows = self.conn.execute("SELECT id FROM scan_roots").fetchall()
        return [self.get_scan_root(r["id"]) for r in rows]

    # -----------------------------------------------------------------------
    # Scans
    # -----------------------------------------------------------------------
    def start_scan(self) -> ScanRun:
        cur = self.conn.execute(
            "INSERT INTO scans (status) VALUES (?)", (ScanStatus.RUNNING.value,)
        )
        self.conn.commit()

        # Assert to narrow int | None -> int for the type checker.
        assert cur.lastrowid is not None
        return self._get_scan(cur.lastrowid)

    def finish_scan(
        self,
        scan_id: int,
        *,
        status: ScanStatus,
        movies_found: int = 0,
        shows_found: int = 0,
        episodes_found: int = 0,
        filesystem_errors: int = 0,
        probe_errors: int = 0,
        hash_errors: int = 0,
    ) -> ScanRun:
        errors_count = filesystem_errors + probe_errors + hash_errors
        self.conn.execute(
            """
            UPDATE scans SET
                ended_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                status = ?,
                movies_found = ?,
                shows_found = ?,
                episodes_found = ?,
                filesystem_errors = ?,
                probe_errors = ?,
                hash_errors = ?,
                errors_count = ?
            WHERE id = ?
            """,
            (
                status.value,
                movies_found,
                shows_found,
                episodes_found,
                filesystem_errors,
                probe_errors,
                hash_errors,
                errors_count,
                scan_id,
            ),
        )
        self.conn.commit()
        return self._get_scan(scan_id)

    def _get_scan(self, scan_id: int) -> ScanRun:
        row = self.conn.execute(
            "SELECT * FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Scan {scan_id} not found")

        return ScanRun(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=ScanStatus(row["status"]),
            movies_found=row["movies_found"],
            shows_found=row["shows_found"],
            episodes_found=row["episodes_found"],
            exact_duplicates_found=row["exact_duplicates_found"],
            near_duplicates_found=row["near_duplicates_found"],
            filesystem_errors=row["filesystem_errors"],
            probe_errors=row["probe_errors"],
            hash_errors=row["hash_errors"],
        )

    # -----------------------------------------------------------------------
    # Media Files
    # -----------------------------------------------------------------------
    def insert_media_file(self, mf: MediaFile) -> MediaFile:
        cur = self.conn.execute(
            """
            INSERT INTO media_files (
                path, filename, extension, kind, size, mtime_ns,
                last_seen_scan_id, missing_since_scan_id,
                parsed_title, parsed_year, parse_status, parse_confidence,
                show_key, season, episode, near_dup_key,
                codec, width, height, duration, bit_rate,
                audio_codec, audio_channels, audio_streams_json,
                has_embedded_subs, embedded_sub_count, embedded_sub_langs
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                str(mf.path),
                mf.filename,
                mf.extension,
                mf.kind.value,
                mf.size,
                mf.mtime_ns,
                mf.last_seen_scan_id,
                mf.missing_since_scan_id,
                mf.parsed_title,
                mf.parsed_year,
                mf.parse_status.value,
                mf.parse_confidence.value,
                mf.show_key,
                mf.season,
                mf.episode,
                mf.near_dup_key,
                mf.codec,
                mf.width,
                mf.height,
                mf.duration,
                mf.bit_rate,
                mf.audio_codec,
                mf.audio_channels,
                mf.audio_streams_json,
                mf.has_embedded_subs,
                mf.embedded_sub_count,
                mf.embedded_sub_langs,
            ),
        )
        self.conn.commit()

        assert cur.lastrowid is not None
        return self.get_media_file(cur.lastrowid)

    def get_media_file(self, mf_id: int) -> MediaFile:
        row = self.conn.execute(
            "SELECT * FROM media_files WHERE id = ?", (mf_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"MediaFile {mf_id} not found")
        return self._row_to_media_file(row)

    def get_media_file_by_path(self, path: Path) -> MediaFile | None:
        row = self.conn.execute(
            "SELECT * FROM media_files WHERE path = ?", (str(path),)
        ).fetchone()
        if not row:
            return None
        return self._row_to_media_file(row)

    def _row_to_media_file(self, row: sqlite3.Row) -> MediaFile:
        return MediaFile(
            id=row["id"],
            path=Path(row["path"]),
            filename=row["filename"],
            extension=row["extension"],
            kind=MediaKind(row["kind"]),
            size=row["size"],
            mtime_ns=row["mtime_ns"],
            last_seen_scan_id=row["last_seen_scan_id"],
            missing_since_scan_id=row["missing_since_scan_id"],
            parsed_title=row["parsed_title"],
            parsed_year=row["parsed_year"],
            parse_status=ParseStatus(row["parse_status"]),
            parse_confidence=ParseConfidence(row["parse_confidence"]),
            show_key=row["show_key"],
            season=row["season"],
            episode=row["episode"],
            near_dup_key=row["near_dup_key"],
            codec=row["codec"],
            width=row["width"],
            height=row["height"],
            duration=row["duration"],
            bit_rate=row["bit_rate"],
            audio_codec=row["audio_codec"],
            audio_channels=row["audio_channels"],
            audio_streams_json=row["audio_streams_json"],
            has_embedded_subs=row["has_embedded_subs"],
            embedded_sub_count=row["embedded_sub_count"],
            embedded_sub_langs=row["embedded_sub_langs"],
            probed_at=row["probed_at"],
            ffprobe_version=row["ffprobe_version"],
        )

    def update_media_file(self, mf: MediaFile) -> None:
        if mf.id is None:
            raise ValueError("Cannot update MediaFile without an id")

        self.conn.execute(
            """
            UPDATE media_files SET
                last_seen_scan_id = ?,
                missing_since_scan_id = ?,
                parsed_title = ?, parsed_year = ?,
                parse_status = ?, parse_confidence = ?,
                show_key = ?, season = ?, episode = ?, near_dup_key = ?,
                codec = ?, width = ?, height = ?, duration = ?, bit_rate = ?,
                audio_codec = ?, audio_channels = ?, audio_streams_json = ?,
                has_embedded_subs = ?, embedded_sub_count = ?, embedded_sub_langs = ?,
                probed_at = ?, ffprobe_version = ?
            WHERE id = ?
            """,
            (
                mf.last_seen_scan_id,
                mf.missing_since_scan_id,
                mf.parsed_title,
                mf.parsed_year,
                mf.parse_status.value,
                mf.parse_confidence.value,
                mf.show_key,
                mf.season,
                mf.episode,
                mf.near_dup_key,
                mf.codec,
                mf.width,
                mf.height,
                mf.duration,
                mf.bit_rate,
                mf.audio_codec,
                mf.audio_channels,
                mf.audio_streams_json,
                mf.has_embedded_subs,
                mf.embedded_sub_count,
                mf.embedded_sub_langs,
                mf.probed_at,
                mf.ffprobe_version,
                mf.id,
            ),
        )
        self.conn.commit()

    # -----------------------------------------------------------------------
    # Scan Membership & Missing Tracking
    # -----------------------------------------------------------------------
    def record_scan_membership(self, scan_id: int, media_file_id: int) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO scan_media_files
                (scan_id, media_file_id)
            VALUES (?, ?)
            """,
            (scan_id, media_file_id),
        )
        self.conn.commit()

    def list_scan_members(self, scan_id: int) -> list[MediaFile]:
        rows = self.conn.execute(
            """
            SELECT m.* FROM media_files m
            JOIN scan_media_files s ON m.id = s.media_file_id
            WHERE s.scan_id = ?
            """,
            (scan_id,),
        ).fetchall()
        return [self._row_to_media_file(r) for r in rows]

    def mark_missing(self, media_file_id: int, scan_id: int) -> None:
        self.conn.execute(
            "UPDATE media_files SET missing_since_scan_id = ? WHERE id = ?",
            (scan_id, media_file_id),
        )
        self.conn.commit()

    def clear_missing(self, media_file_id: int) -> None:
        self.conn.execute(
            "UPDATE media_files SET missing_since_scan_id = NULL WHERE id = ?",
            (media_file_id,),
        )
        self.conn.commit()
