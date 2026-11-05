""""""

import pytest
from mediavault.paths import validate_path


def test_validate_path_with_existing_directory(tmp_path):
    """An existing directory passes validation."""
    assert validate_path(tmp_path) is None


def test_validate_path_with_nonexistent_path(tmp_path):
    """A nonexistent path raises ValueError."""
    path = tmp_path / "does_not_exist"

    with pytest.raises(ValueError):
        validate_path(path)


def test_validate_path_with_file(tmp_path):
    """A file raises ValueError when a directory is required."""
    path = tmp_path / "file.txt"
    path.touch()

    with pytest.raises(ValueError):
        validate_path(path)


def test_validate_path_symlink_to_file_rejected(tmp_path):
    target = tmp_path / "file.txt"
    target.touch()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        validate_path(link)
