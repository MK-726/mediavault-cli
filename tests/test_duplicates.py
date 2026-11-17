"""Exact duplicate detection tests (FR-700–FR-706)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.config.schema import Config, DuplicatesConfig, GeneralConfig, ScanConfig
from mediavault.duplicates import find_exact_duplicates
from mediavault.models import MediaFile, MediaKind


@pytest.fixture
def cfg() -> Config:
    return Config(
        general=GeneralConfig(
            db_path="m.db",
            log_dir="logs",
            log_level="DEBUG",
            ffprobe_path="ffprobe",
            ffprobe_timeout_seconds=60,
            ffprobe_stderr_max_chars=2000,
            subs_dir_name="subs",
            report_output_dir="reports",
            probe_skip_unchanged=True,
            follow_symlinks=False,
            include_hidden=False,
            skip_dirs=[],
        ),
        scan=ScanConfig(),
        duplicates=DuplicatesConfig(
            hash_chunk_bytes=1024,  # Small chunks for testing
            partial_hash_bytes=10,  # Very small partial chunk for testing
        ),
    )


def _create_dummy_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _mf(path: Path) -> MediaFile:
    return MediaFile(
        path=path,
        filename=path.name,
        extension=path.suffix.lower(),
        kind=MediaKind.MOVIE,
        size=path.stat().st_size,
        mtime_ns=path.stat().st_mtime_ns,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_no_duplicates(tmp_path, cfg):
    f1 = _create_dummy_file(tmp_path / "a.mkv", b"content A" * 10)
    f2 = _create_dummy_file(tmp_path / "b.mkv", b"content B" * 10)

    mfs = [_mf(f1), _mf(f2)]
    groups = find_exact_duplicates(mfs, cfg)

    assert len(groups) == 0


def test_exact_duplicates_same_size(tmp_path, cfg):
    content = b"identical content" * 100
    f1 = _create_dummy_file(tmp_path / "a.mkv", content)
    f2 = _create_dummy_file(tmp_path / "b.mkv", content)

    mfs = [_mf(f1), _mf(f2)]
    mfs[0].id = 1
    mfs[1].id = 2

    groups = find_exact_duplicates(mfs, cfg)

    assert len(groups) == 1
    group = groups[0]
    assert len(group) == 2
    assert group[0].hash_value == group[1].hash_value
    assert {m.media_file_id for m in group} == {1, 2}


def test_different_content_same_size_no_dup(tmp_path, cfg):
    # Same size (14 bytes), completely different content
    f1 = _create_dummy_file(tmp_path / "a.mkv", b"0123456789ABCD")
    f2 = _create_dummy_file(tmp_path / "b.mkv", b"9876543210ZYXW")

    mfs = [_mf(f1), _mf(f2)]
    groups = find_exact_duplicates(mfs, cfg)

    # They should be caught by the partial hash and skipped for full hash
    assert len(groups) == 0


def test_different_size_no_dup(tmp_path, cfg):
    # Different sizes, same prefix
    f1 = _create_dummy_file(tmp_path / "a.mkv", b"same prefix" + b"A" * 50)
    f2 = _create_dummy_file(tmp_path / "b.mkv", b"same prefix" + b"B" * 60)

    mfs = [_mf(f1), _mf(f2)]
    groups = find_exact_duplicates(mfs, cfg)

    # Caught by size grouping, never hashed
    assert len(groups) == 0


def test_three_duplicates(tmp_path, cfg):
    content = b"three copies" * 10
    f1 = _create_dummy_file(tmp_path / "a.mkv", content)
    f2 = _create_dummy_file(tmp_path / "b.mkv", content)
    f3 = _create_dummy_file(tmp_path / "c.mkv", content)

    mfs = [_mf(f1), _mf(f2), _mf(f3)]
    mfs[0].id = 1
    mfs[1].id = 2
    mfs[2].id = 3

    groups = find_exact_duplicates(mfs, cfg)

    assert len(groups) == 1
    assert len(groups[0]) == 3
