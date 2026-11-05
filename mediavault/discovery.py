""""""

from pathlib import Path
from mediavault.constants import SUPPORTED_VIDEO_EXTENTIONS


def discover_movie_files(root: str | Path) -> list[Path]:
    """Discover all MKV and MP4 files."""

    return _iter_video_files(root)


def discover_shows(root: str | Path) -> list[Path]:
    """Discover all show directories."""

    directory = Path(root)
    shows: list[Path] = []

    for item in directory.iterdir():
        if item.is_dir():
            shows.append(item)

    return shows


def discover_episode_files(show_dir: str | Path) -> list[Path]:
    """Discover all episode files in a show directory."""

    return _iter_video_files(show_dir)


def _iter_video_files(root: str | Path) -> list[Path]:
    """Discover video files recursively."""

    directory = Path(root)
    files: list[Path] = []

    for file in directory.rglob("*"):
        if file.is_file() and file.suffix.lower() in SUPPORTED_VIDEO_EXTENTIONS:
            files.append(file)

    return files
