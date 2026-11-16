"""Technical metadata extraction via FFprobe (FR-500–FR-507)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from mediavault.config.schema import Config
from mediavault.logging_setup import get_logger
from mediavault.models import MediaFile

_log = get_logger("metadata")


def check_ffprobe_available(config: Config) -> bool:
    """Return True if the configured ffprobe executable exists on PATH."""
    path = config.general.ffprobe_path
    # If it's an absolute path, check if it exists; otherwise use shutil.which
    if "/" in path:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which(path) is not None


def extract_metadata(media_file: MediaFile, config: Config) -> MediaFile:
    """Run FFprobe on *media_file* and populate its metadata fields (in place).

    Returns the mutated MediaFile.
    """
    cmd = [
        config.general.ffprobe_path,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(media_file.path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.general.ffprobe_timeout_seconds,
            check=False,  # We handle non-zero exit codes manually
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "metadata: ffprobe timeout for %s after %ds",
            media_file.path,
            config.general.ffprobe_timeout_seconds,
        )
        _handle_failure(media_file, "timeout")
        return media_file
    except Exception as exc:
        _log.warning(
            "metadata: ffprobe execution failed for %s: %s", media_file.path, exc
        )
        _handle_failure(media_file, "execution_error")
        return media_file

    if result.returncode != 0:
        stderr_snippet = result.stderr[: config.general.ffprobe_stderr_max_chars]
        _log.warning(
            "metadata: ffprobe non-zero exit for %s (code %d): %s",
            media_file.path,
            result.returncode,
            stderr_snippet,
        )
        _handle_failure(media_file, "non_zero_exit")
        return media_file

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _log.warning("metadata: failed to parse JSON for %s: %s", media_file.path, exc)
        _handle_failure(media_file, "bad_json")
        return media_file

    # --- Parse format ---
    fmt = data.get("format", {})
    try:
        media_file.duration = float(fmt["duration"]) if "duration" in fmt else None
        media_file.bit_rate = int(fmt["bit_rate"]) if "bit_rate" in fmt else None
    except ValueError, TypeError:
        pass  # Leave as None if malformed

    # --- Parse streams ---
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    # Video (first stream)
    if video_streams:
        v = video_streams[0]
        media_file.codec = v.get("codec_name")
        media_file.width = v.get("width")
        media_file.height = v.get("height")

    # Audio (first stream for summary fields, all streams for JSON)
    if audio_streams:
        a = audio_streams[0]
        media_file.audio_codec = a.get("codec_name")
        media_file.audio_channels = a.get("channels")

        # FR-501: additional streams' summaries stored as JSON
        audio_summaries = []
        for stream in audio_streams:
            summary = {
                "codec": stream.get("codec_name"),
                "channels": stream.get("channels"),
                "language": stream.get("tags", {}).get("language"),
            }
            audio_summaries.append(summary)
        media_file.audio_streams_json = json.dumps(audio_summaries)

    # Subtitles (FR-501, FR-600)
    if sub_streams:
        media_file.has_embedded_subs = True
        media_file.embedded_sub_count = len(sub_streams)

        langs = []
        for sub in sub_streams:
            lang = sub.get("tags", {}).get("language")
            if lang:
                langs.append(lang)

        if langs:
            media_file.embedded_sub_langs = ",".join(langs)
    else:
        media_file.has_embedded_subs = False
        media_file.embedded_sub_count = 0
        media_file.embedded_sub_langs = None

    return media_file


def _handle_failure(media_file: MediaFile, reason: str) -> None:
    """Set all probe fields to NULL on failure (FR-503, FR-506)."""
    media_file.codec = None
    media_file.width = None
    media_file.height = None
    media_file.duration = None
    media_file.bit_rate = None
    media_file.audio_codec = None
    media_file.audio_channels = None
    media_file.audio_streams_json = None
    media_file.has_embedded_subs = None
    media_file.embedded_sub_count = None
    media_file.embedded_sub_langs = None
    media_file.probed_at = None
    media_file.ffprobe_version = None
