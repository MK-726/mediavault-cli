"""Models module tests: StrEnum values, defaults, error-count property."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.constants import (
    DUPLICATE_GROUP_KINDS,
    MEDIA_KINDS,
    PARSE_STATUSES,
    ROOT_TYPES,
    SCAN_STATUSES,
    SUBTITLE_KINDS,
)
from mediavault.models import (
    DuplicateKind,
    MediaFile,
    MediaKind,
    ParseStatus,
    RootType,
    ScanRun,
    ScanStatus,
    SubtitleKind,
)


@pytest.mark.parametrize(
    "enum_cls, allowed",
    [
        (MediaKind, MEDIA_KINDS),
        (ScanStatus, SCAN_STATUSES),
        (SubtitleKind, SUBTITLE_KINDS),
        (ParseStatus, PARSE_STATUSES),
        (DuplicateKind, DUPLICATE_GROUP_KINDS),
        (RootType, ROOT_TYPES),
    ],
)
def test_enum_values_match_constants(enum_cls, allowed):
    """Python enums and SQL CHECK tuples must agree (FR-810)."""
    assert {member.value for member in enum_cls} == set(allowed)


def test_scan_run_errors_count_aggregates():
    run = ScanRun(filesystem_errors=2, probe_errors=3, hash_errors=1)
    assert run.errors_count == 6


def test_media_file_minimal():
    mf = MediaFile(
        path=Path("/x.mkv"),
        filename="x.mkv",
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=1,
        mtime_ns=2,
    )
    assert mf.parse_status is ParseStatus.UNPARSED
    assert mf.has_embedded_subs is None  # FR-507: unknown, not False
    assert mf.id is None


def test_media_file_embedded_subs_tristate():
    mf = MediaFile(
        path=Path("/x.mkv"), filename="x.mkv", extension=".mkv",
        kind=MediaKind.MOVIE, size=1, mtime_ns=2,
        has_embedded_subs=False,
    )
    assert mf.has_embedded_subs is False
