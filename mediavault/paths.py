""""""

from pathlib import Path


def validate_path(path: str) -> None:
    """Raise ValueError if the path does not exist or is not a directory."""
    directory = Path(path)

    if not directory.exists():
        raise ValueError(f"Path does not exist: {path}")

    if not directory.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
