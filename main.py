'''main.py'''


from pathlib import Path

from helpers import discover_video_files


def validate_path(path: str) -> None:
    """Raise ValueError if the path does not exist or is not a directory."""
    directory = Path(path)

    if not directory.exists():
        raise ValueError(f"Path does not exist: {path}")

    if not directory.is_dir():
        raise ValueError(f"Path is not a directory: {path}")


def discover_movie_files(path: str | Path) -> list[Path]:
    """Discover all MKV and MP4 files."""

    return discover_video_files(path)


def discover_shows(path: str | Path) -> list[Path]:
    """Discover all show directories."""

    directory = Path(path)
    shows: list[Path] = []

    for item in directory.iterdir():
        if item.is_dir():
            shows.append(item)

    return shows


def discover_episode_files(path: str | Path) -> list[Path]:
    """Discover all episode files in a show directory."""

    return discover_video_files(path)
