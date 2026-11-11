"""
Path validation and canonicalization tests (FR-300–FR-304, FR-321, FR-322, FR-1110).
"""

from __future__ import annotations

import pytest

from mediavault.errors import PathValidationError
from mediavault.paths import (
    canonicalize_and_dedupe_roots,
    expand_path,
    is_inside_scan_root,
    is_root_mounted,
    validate_directory,
    validate_path,
)


# ---------------------------------------------------------------------------
# expand_path
# ---------------------------------------------------------------------------
def test_expand_path_expands_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = expand_path("~/Movies")
    assert p == (tmp_path / "Movies").absolute()


def test_expand_path_does_not_require_existence(tmp_path):
    p = expand_path(tmp_path / "does-not-exist")
    assert p.is_absolute()
    assert not p.exists()  # untouched, not created


def test_expand_path_makes_absolute(tmp_path):
    p = expand_path("relative/path")
    assert p.is_absolute()


# ---------------------------------------------------------------------------
# validate_directory
# ---------------------------------------------------------------------------
def test_validate_directory_ok(tmp_path):
    d = tmp_path / "movies"
    d.mkdir()
    assert validate_directory(d) == d.resolve()


def test_validate_directory_missing(tmp_path):
    with pytest.raises(PathValidationError, match="does not exist"):
        validate_directory(tmp_path / "nope")


def test_validate_directory_rejects_file(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    with pytest.raises(PathValidationError, match="not a directory"):
        validate_directory(f)


def test_validate_directory_resolves_symlink_to_dir(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert validate_directory(link) == real.resolve()


def test_validate_directory_rejects_symlink_to_file(tmp_path):
    target = tmp_path / "a.mkv"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PathValidationError, match="not a directory"):
        validate_directory(link)


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------
def test_validate_path_file_ok(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    assert validate_path(f) == f.resolve()


def test_validate_path_missing(tmp_path):
    with pytest.raises(PathValidationError):
        validate_path(tmp_path / "nope")


# ---------------------------------------------------------------------------
# canonicalize_and_dedupe_roots
# ---------------------------------------------------------------------------
def test_canonicalize_dedupes_exact_duplicates(tmp_path):
    d = tmp_path / "movies"
    d.mkdir()
    assert canonicalize_and_dedupe_roots([d, d]) == [d.resolve()]


def test_canonicalize_drops_descendants(tmp_path):
    parent = tmp_path / "media"
    child = parent / "movies"
    child.mkdir(parents=True)
    assert canonicalize_and_dedupe_roots([parent, child]) == [parent.resolve()]
    # order-preserving: child-first still drops child
    assert canonicalize_and_dedupe_roots([child, parent]) == [parent.resolve()]


def test_canonicalize_keeps_unrelated_roots(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert canonicalize_and_dedupe_roots([a, b]) == [a.resolve(), b.resolve()]


def test_canonicalize_prefix_is_not_confused_for_ancestor(tmp_path):
    # "/foo" and "/foobar" are unrelated — the classic startswith() bug.
    a = tmp_path / "foo"
    b = tmp_path / "foobar"
    a.mkdir()
    b.mkdir()
    assert canonicalize_and_dedupe_roots([a, b]) == [a.resolve(), b.resolve()]


def test_canonicalize_resolves_symlinks_before_compare(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert canonicalize_and_dedupe_roots([real, link]) == [real.resolve()]


# ---------------------------------------------------------------------------
# is_root_mounted
# ---------------------------------------------------------------------------
def test_is_root_mounted_true(tmp_path):
    assert is_root_mounted(tmp_path) is True


def test_is_root_mounted_false_when_missing(tmp_path):
    assert is_root_mounted(tmp_path / "unplugged") is False


def test_is_root_mounted_false_for_file(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    assert is_root_mounted(f) is False


# ---------------------------------------------------------------------------
# is_inside_scan_root
# ---------------------------------------------------------------------------
def test_is_inside_scan_root_true_for_root_itself(tmp_path):
    root = tmp_path / "movies"
    root.mkdir()
    assert is_inside_scan_root(root, [root]) is True


def test_is_inside_scan_root_true_for_descendant(tmp_path):
    root = tmp_path / "movies"
    sub = root / "reports"
    sub.mkdir(parents=True)
    assert is_inside_scan_root(sub, [root]) is True


def test_is_inside_scan_root_false_for_sibling(tmp_path):
    root = tmp_path / "movies"
    sibling = tmp_path / "reports"
    root.mkdir()
    sibling.mkdir()
    assert is_inside_scan_root(sibling, [root]) is False


def test_is_inside_scan_root_prefix_bug(tmp_path):
    # "/foo" must not be considered inside "/foobar".
    a = tmp_path / "foo"
    b = tmp_path / "foobar"
    a.mkdir()
    b.mkdir()
    assert is_inside_scan_root(a, [b]) is False
    assert is_inside_scan_root(b, [a]) is False


def test_is_inside_scan_root_through_symlink(tmp_path):
    root = tmp_path / "movies"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    # A symlink inside the root pointing outside should resolve outside;
    # a symlink outside pointing into the root should resolve inside.
    link = outside / "into-root"
    link.symlink_to(root / "reports" if False else root, target_is_directory=True)
    # link resolves to root → it IS inside
    assert is_inside_scan_root(link, [root]) is True
