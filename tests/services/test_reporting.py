"""Report runner service tests (FR-1101, FR-1105, FR-1109)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediavault.database.connection import connect
from mediavault.database.migrator import migrate
from mediavault.database.repository import Repository
from mediavault.errors import UsageError
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)
from mediavault.reports.base import ReportScope
from mediavault.services.reporting import build_report_data, export_reports


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    yield Repository(conn)
    conn.close()


@pytest.fixture
def seeded(repo):
    """Populate the DB with a small mixed library."""
    # (Same fixture logic as test_library.py)
    repo.start_scan()

    def add(path: str, **kwargs) -> MediaFile:
        mf = MediaFile(
            path=Path(path),
            filename=Path(path).name,
            extension=Path(path).suffix.lower(),
            kind=kwargs.pop("kind", MediaKind.MOVIE),
            size=100,
            mtime_ns=1,
            parse_status=kwargs.pop("parse_status", ParseStatus.OK),
            parse_confidence=kwargs.pop("parse_confidence", ParseConfidence.HIGH),
            **kwargs,
        )
        return repo.insert_media_file(mf)

    m1 = add("/lib/a.mkv", parsed_title="A Movie", parsed_year=2020)
    add("/lib/b.mkv", parsed_title="B Movie", parsed_year=2021)

    e1 = add(
        "/lib/Show/Season-1/Show.S01E01.mkv",
        kind=MediaKind.EPISODE,
        show_key="show",
        season=1,
        episode=1,
        parsed_title="Show",
    )

    # Add an external sub to m1 and e1
    repo.conn.execute(
        "INSERT INTO subtitles (media_file_id, path, kind, is_primary) "
        "VALUES (?, ?, 'external', 1)",
        (m1.id, "/lib/a.srt"),
    )
    repo.conn.execute(
        "INSERT INTO subtitles (media_file_id, path, kind, is_primary) "
        "VALUES (?, ?, 'external', 1)",
        (e1.id, "/lib/Show/Season-1/S.S01E01.srt"),
    )
    repo.conn.commit()

    return repo


def test_build_report_data_full(seeded):
    data = build_report_data(seeded, scope=ReportScope.FULL)

    assert data.scope == ReportScope.FULL
    assert len(data.movies) == 2
    assert len(data.episodes) == 1
    assert data.files_with_external_subs == frozenset({1, 3})
    assert data.generated_at != ""  # should have a timestamp


def test_build_report_data_movies(seeded):
    data = build_report_data(seeded, scope=ReportScope.MOVIES)
    assert len(data.movies) == 2
    assert len(data.episodes) == 0


def test_build_report_data_show(seeded):
    data = build_report_data(seeded, scope=ReportScope.SHOW, show_key="show")
    assert len(data.movies) == 0
    assert len(data.episodes) == 1


def test_build_report_data_show_requires_key(seeded):
    with pytest.raises(UsageError, match="--show"):
        build_report_data(seeded, scope=ReportScope.SHOW, show_key=None)


def test_export_reports_txt(seeded, tmp_path):
    data = build_report_data(seeded, scope=ReportScope.FULL)
    paths = export_reports(data, format="txt", output_dir=tmp_path)

    assert len(paths) == 1
    assert paths[0].suffix == ".txt"
    assert paths[0].exists()
    assert "A Movie" in paths[0].read_text()


def test_export_reports_csv(seeded, tmp_path):
    data = build_report_data(seeded, scope=ReportScope.FULL)
    paths = export_reports(data, format="csv", output_dir=tmp_path)

    assert len(paths) == 3
    assert all(p.suffix == ".csv" for p in paths)
    names = {p.name for p in paths}
    assert any("-movies" in n for n in names)
    assert any("-episodes" in n for n in names)
    assert any("-problems" in n for n in names)
