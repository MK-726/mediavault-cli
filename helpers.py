"""Helper functions."""

from pathlib import Path

VIDEO_EXTENTIONS = {".mkv", ".mp4"}


def discover_video_files(path: str | Path) -> list[Path]:
    """Discover video files recursively."""

    directory = Path(path)
    files: list[Path] = []

    for file in directory.rglob("*"):
        if file.is_file() and file.suffix.lower() in VIDEO_EXTENTIONS:
            files.append(file)

    return files
