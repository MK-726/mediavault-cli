"""Filename and directory-name parsing (FR-400–FR-422).

Part 1 (this file, core):
  * normalization (display form and match key) — FR-402, FR-410
  * junk-token stripping — FR-401
  * movie parsing — FR-400–FR-404

Part 2 (appended next):
  * episode parsing, directory-wins rules — FR-410–FR-418
  * apply_parsing(media_files, ...) entry point

Parsing is deterministic and filesystem-free (FR-422). It never raises on
malformed input (FR-420): failures set parse_status=UNPARSED instead.

This module is UI-agnostic (NFR-015) and stdlib-only apart from
mediavault.constants and mediavault.models.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from mediavault.constants import (
    EPISODE_1X02_RE,
    EPISODE_LONG_RE,
    EPISODE_SXXEXX_RE,
    JUNK_TOKENS,
    VIDEO_EXTENSIONS,
    WORD_SEPARATORS_RE,
    parse_season_dir,
)
from mediavault.logging_setup import get_logger
from mediavault.models import (
    MediaFile,
    MediaKind,
    ParseConfidence,
    ParseStatus,
)

_log = get_logger("parsing")


def to_display_title(raw: str) -> str:
    """Return the human-readable display form of a title (FR-402).

    Steps:
      1. Replace runs of whitespace, '.', '_', '-' with a single space.
      2. Drop every remaining character that is not Unicode-alphanumeric
         or whitespace (this is what drops apostrophes, colons, etc.,
         WITHOUT treating them as separators).
      3. Collapse whitespace and trim.
      4. Title-case each token.

    Unicode-aware: ``Amélie`` stays ``Amélie``. All-caps tokens are not
    preserved by design (no FR requires it); str.title() is used.
    """
    s = WORD_SEPARATORS_RE.sub(" ", raw)
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
    s = " ".join(s.split())
    if not s:
        return ""
    return " ".join(token.title() for token in s.split(" "))


def to_match_key(raw: str) -> str:
    """Return the equality-form key used for near-dup grouping (FR-402).

    Lowercase the display form, replace spaces with underscores.
    ``A.Clockwork.Orange`` → ``a_clockwork_orange``.
    """
    display = to_display_title(raw)
    return display.lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# Junk-token stripping (FR-401)
# ---------------------------------------------------------------------------
# Deterministic, longest-first ordering. Substring junk tokens (e.g.
# 'web' is a prefix of 'web-dl') must be applied after their longer
# counterparts, otherwise 'web' splits 'WEB-DL' before 'web-dl' can match.
_JUNK_PATTERNS = tuple(
    re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    for token in sorted(JUNK_TOKENS, key=lambda t: (-len(t), t))
)


def strip_junk_tokens(raw: str) -> str:
    """Remove tokens matching the junk denylist (FR-401).

    Matches each denylist entry against the raw string, bounded by
    non-alphanumeric characters (or string start/end), case-insensitively.
    This correctly handles hyphenated ('web-dl', 'blu-ray') and dotted
    ('h.264') junk tokens, while leaving hyphenated *titles* like
    'Spider-Man' intact (they aren't on the denylist).

    After removing matches, the surviving text is split on the standard
    word separators and rejoined with single spaces.
    """
    if not raw:
        return raw
    for pattern in _JUNK_PATTERNS:
        raw = pattern.sub(" ", raw)
    return " ".join(re.split(r"[\s._-]+", raw)).strip()


# ---------------------------------------------------------------------------
# Movie parsing (FR-400–FR-404)
# ---------------------------------------------------------------------------
# The four patterns, applied in order. All are anchored and case-sensitive
# for the "(YYYY)" parentheses form, insensitive for the year-only form
# (some libraries use just ".2020.").
#
# Pattern 1: Title (Year) [junk].ext
_MOVIE_PAREN_YEAR_RE = re.compile(
    r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)(?:\s*\[[^\]]*\])?\s*$"
)
# Patterns 2-4 are one regex that strips a trailing year and any remaining
# ".resolution.source.codec" tail. The junk list handles the tail; this
# regex only extracts title and year.
_MOVIE_YEAR_TAIL_RE = re.compile(
    r"^(?P<title>.+)[.\s_-](?P<year>(?:19|20)\d{2})(?=[.\s_-]|$)(?:[.\s_-].*)?$"
)


def _extract_movie_title_year(stem: str) -> tuple[str, int | None] | None:
    """Try all four patterns in order; return (raw_title, year) or None."""
    if not stem:
        return None

    # Pattern 1: "Title (Year) [junk]"
    m = _MOVIE_PAREN_YEAR_RE.match(stem)
    if m:
        return (m.group("title").strip(), int(m.group("year")))

    # Patterns 2-4: all share "Title.<year>..." shape
    m = _MOVIE_YEAR_TAIL_RE.match(stem)
    if m:
        return (m.group("title").strip(), int(m.group("year")))

    # No year found. That's a legitimate "partial" outcome (FR-421).
    return None


def parse_movie(media_file: MediaFile) -> MediaFile:
    """Parse a movie MediaFile in place and return it.

    Fills ``parsed_title`` (display form) and ``parsed_year``. The match
    key is *not* stored on MediaFile — it's derived from parsed_title via
    ``to_match_key`` where needed (near-dup grouping, Phase 11). This
    keeps the model free of redundant derived fields.

    Sets:
      * parse_status=OK       — title and year both found
      * parse_status=PARTIAL  — title found, no year
      * parse_status=UNPARSED — neither found
      * parse_confidence      — HIGH if OK and title has >1 word,
                                MEDIUM if OK and title is 1 word,
                                LOW otherwise

    Never raises (FR-420). Does not touch the filesystem (FR-422).
    """
    # We can't rely on Path.stem for adversarial filenames: for
    # "...mkv", pathlib doesn't treat ".mkv" as a suffix, so stem ==
    # the full name. Use the extension from discovery, with a fallback
    # that detects a trailing known video extension directly. This
    # matters when MediaFile.extension is empty (e.g. hand-constructed
    # in tests, or if a future discovery path fails to set it).
    stem = media_file.filename
    ext = media_file.extension
    if not ext:
        lower = stem.lower()
        for known in VIDEO_EXTENSIONS:
            if lower.endswith(known):
                ext = known
                break
    if ext and stem.lower().endswith(ext.lower()):
        stem = stem[: -len(ext)]

    stem = strip_junk_tokens(stem)
    # Defensive: degenerate inputs ('..', '...', '-_-') leave only
    # separator/whitespace characters after junk-stripping. Treat these
    # as immediate UNPARSED, before hitting the regexes (FR-420).
    if not stem.strip(" ._-"):
        media_file.parse_status = ParseStatus.UNPARSED
        media_file.parse_confidence = ParseConfidence.LOW
        _log.debug("parse_movie: unparsed (empty stem) for %s", media_file.path)
        return media_file

    extracted = _extract_movie_title_year(stem)
    if extracted is None:
        # No year. Try to still recover a title for PARTIAL status.
        display = to_display_title(stem)
        if display:
            media_file.parsed_title = display
            media_file.parsed_year = None
            media_file.parse_status = ParseStatus.PARTIAL
            media_file.parse_confidence = ParseConfidence.LOW
            _log.debug("parse_movie: partial (no year) for %s", media_file.path)
        else:
            media_file.parse_status = ParseStatus.UNPARSED
            media_file.parse_confidence = ParseConfidence.LOW
            _log.debug("parse_movie: unparsed for %s", media_file.path)
        return media_file

    raw_title, year = extracted
    display = to_display_title(raw_title)
    if not display:
        media_file.parse_status = ParseStatus.UNPARSED
        media_file.parse_confidence = ParseConfidence.LOW
        _log.debug("parse_movie: unparsed (empty title) for %s", media_file.path)
        return media_file

    media_file.parsed_title = display
    media_file.parsed_year = year
    media_file.parse_status = ParseStatus.OK
    media_file.parse_confidence = (
        ParseConfidence.HIGH if " " in display else ParseConfidence.MEDIUM
    )
    _log.debug(
        "parse_movie: ok %r (%d) for %s",
        display,
        year,
        media_file.path,
    )
    return media_file


# ---------------------------------------------------------------------------
# Episode parsing (FR-410–FR-418)
# ---------------------------------------------------------------------------
_EPISODE_PATTERNS = (EPISODE_SXXEXX_RE, EPISODE_1X02_RE, EPISODE_LONG_RE)


def _split_episode_identity(path: Path, root: Path) -> tuple[Path | None, Path | None]:
    """Walk up from *path* to *root*; return (show_dir, season_dir).

    show_dir is the first-level subdirectory of *root* that contains the
    file (FR-313); season_dir is the innermost valid Season-* ancestor
    strictly between show_dir and the file (FR-415).

    Both are None if *path* is not under *root*. They are returned as
    Path objects that may not exist on disk (parsing is filesystem-free,
    FR-422) — the caller has already verified existence during discovery.
    """
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return (None, None)

    parts = rel.parts
    if len(parts) < 2:
        # File directly under root; no show directory.
        return (None, None)

    show_dir = root / parts[0]

    # Find the innermost ancestor that is a valid Season-* directory,
    # stopping before show_dir itself.
    season_dir: Path | None = None
    current = root
    for part in parts[:-1]:  # exclude the filename
        current = current / part
        if current == show_dir:
            continue
        if parse_season_dir(current.name) is not None:
            season_dir = current  # keep overwriting → innermost wins

    return (show_dir, season_dir)


def _match_episode_pattern(name: str) -> re.Match[str] | None:
    """Return the first matching episode pattern group set, or None."""
    for pattern in _EPISODE_PATTERNS:
        m = pattern.match(name)
        if m:
            return m
    return None


def parse_episode(media_file: MediaFile, *, root: Path) -> MediaFile:
    """Parse an episode MediaFile in place and return it.

    Derives (show, season, episode) from the file's path and the scan
    root, applying directory-wins rules (FR-414, FR-414a).

    Fills ``parsed_title`` (display form of the show name),
    ``show_key`` (match key), ``season``, ``episode``.

    Sets:
      * parse_status=OK       — show + season + episode all found
      * parse_status=PARTIAL  — season derivable, but episode missing
                                (file is inside a Season-* dir; FR-416)
      * parse_status=UNPARSED — no episode found and no Season-* dir
                                (FR-418); show/season may still be filled

    Never raises (FR-420). Does not touch the filesystem (FR-422).
    """
    show_dir, season_dir = _split_episode_identity(media_file.path, root)

    # Show identity comes from the directory (FR-410 / FR-414).
    # If the file is not under the root at all, fall back to the filename.
    if show_dir is not None:
        show_raw = show_dir.name
    else:
        # Defensive: derive show from filename via the episode pattern.
        m = _match_episode_pattern(media_file.filename)
        show_raw = m.group("show") if m else ""

    display = to_display_title(show_raw)
    if display:
        media_file.parsed_title = display
        media_file.show_key = to_match_key(show_raw)

    # Season number (FR-411, FR-414a).
    season: int | None = None
    season_source: str | None = None
    if season_dir is not None:
        season = parse_season_dir(season_dir.name)
        season_source = "directory"

    # Episode number (FR-412/FR-413).
    m = _match_episode_pattern(media_file.filename)
    episode: int | None = None
    if m is not None:
        if season is None:
            # Only fall back to filename season if no valid Season-* dir.
            try:
                season = int(m.group("season"))
                season_source = "filename"
            except IndexError, ValueError:
                season = None
        try:
            episode = int(m.group("episode"))
        except IndexError, ValueError:
            episode = None

    media_file.season = season
    media_file.episode = episode

    # Status + confidence.
    if episode is not None and season is not None:
        media_file.parse_status = ParseStatus.OK
        media_file.parse_confidence = (
            ParseConfidence.HIGH
            if season_source == "directory"
            else ParseConfidence.MEDIUM
        )
    elif episode is None and season_dir is not None:
        # FR-416: in a Season-* dir, no episode number → PARTIAL.
        media_file.parse_status = ParseStatus.PARTIAL
        media_file.parse_confidence = ParseConfidence.LOW
    else:
        # FR-418: no episode + not in a Season-* dir → UNPARSED.
        media_file.parse_status = ParseStatus.UNPARSED
        media_file.parse_confidence = ParseConfidence.LOW

    _log.debug(
        "parse_episode: %s show=%r season=%r episode=%r status=%s",
        media_file.path,
        media_file.parsed_title,
        media_file.season,
        media_file.episode,
        media_file.parse_status.value,
    )
    return media_file


# ---------------------------------------------------------------------------
# Dispatch entry point (used by services/scanner.py in Phase 7)
# ---------------------------------------------------------------------------
def apply_parsing(media_files: list[MediaFile], *, root: Path) -> list[MediaFile]:
    """Parse every MediaFile and return a new list of new objects.

    Per assumption 3 = B: the caller's list and its elements are NOT
    mutated. Each element is shallow-copied via dataclasses.replace (safe
    because MediaFile holds only primitives/Path/enums), then parsed, and
    the parsed copies are returned.

    Dispatch is by ``media_file.kind``:
      * MOVIE   → parse_movie
      * EPISODE → parse_episode(media_file, root=root)
    """
    parsed: list[MediaFile] = []
    for original in media_files:
        copy = dataclasses.replace(original)
        if copy.kind == MediaKind.MOVIE:
            parse_movie(copy)
        else:
            parse_episode(copy, root=root)
        parsed.append(copy)
    return parsed
