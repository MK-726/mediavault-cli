"""FFprobe metadata extraction tests (FR-500–FR-507)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from mediavault.config.schema import Config, DuplicatesConfig, GeneralConfig, ScanConfig
from mediavault.metadata import check_ffprobe_available, extract_metadata
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
        duplicates=DuplicatesConfig(hash_chunk_bytes=1048576, partial_hash_bytes=65536),
    )


@pytest.fixture
def mf(tmp_path) -> MediaFile:
    p = tmp_path / "movie.mkv"
    p.write_bytes(b"dummy data")
    return MediaFile(
        path=p,
        filename=p.name,
        extension=".mkv",
        kind=MediaKind.MOVIE,
        size=10,
        mtime_ns=20,
    )


def _mock_ffprobe_output(stdout_data: dict, returncode: int = 0) -> str:
    return json.dumps(stdout_data)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_extract_metadata_parses_json(monkeypatch, cfg, mf):
    fake_json = {
        "format": {
            "format_name": "matroska,webm",
            "duration": "120.5",
            "bit_rate": "5000000",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": "eng"},
            },
            {
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 6,
                "tags": {"language": "fre"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "spa"},
            },
        ],
    }

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _mock_ffprobe_output(fake_json)
    monkeypatch.setattr(subprocess, "run", mock_run)

    result = extract_metadata(mf, cfg)

    assert result.codec == "h264"
    assert result.width == 1920
    assert result.height == 1080
    assert result.duration == 120.5
    assert result.bit_rate == 5000000
    assert result.audio_codec == "aac"  # first audio stream
    assert result.audio_channels == 2
    assert result.has_embedded_subs is True
    assert result.embedded_sub_count == 2
    assert result.embedded_sub_langs == "eng,spa"

    # The first audio stream summary should be saved as JSON
    assert result.audio_streams_json is not None
    audio_streams = json.loads(result.audio_streams_json)
    assert len(audio_streams) == 2
    assert audio_streams[0]["language"] == "eng"
    assert audio_streams[1]["language"] == "fre"


def test_extract_metadata_no_subtitles(monkeypatch, cfg, mf):
    fake_json = {
        "format": {"format_name": "matroska"},
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160}
        ],
    }

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _mock_ffprobe_output(fake_json)
    monkeypatch.setattr(subprocess, "run", mock_run)

    result = extract_metadata(mf, cfg)

    assert result.has_embedded_subs is False
    assert result.embedded_sub_count == 0
    assert result.embedded_sub_langs is None


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------
def test_extract_metadata_failure_returns_null_fields(monkeypatch, cfg, mf):
    mock_run = MagicMock()
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "ffprobe failed with error"
    monkeypatch.setattr(subprocess, "run", mock_run)

    result = extract_metadata(mf, cfg)

    assert result.codec is None
    assert result.width is None
    assert result.has_embedded_subs is None
    # The error should be handled gracefully, no exception raised


def test_extract_metadata_timeout(monkeypatch, cfg, mf):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = extract_metadata(mf, cfg)
    assert result.codec is None


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------
def test_check_ffprobe_available_true(monkeypatch, cfg):
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/ffprobe")
    assert check_ffprobe_available(cfg) is True


def test_check_ffprobe_available_false(monkeypatch, cfg):
    monkeypatch.setattr("shutil.which", lambda x: None)
    assert check_ffprobe_available(cfg) is False
