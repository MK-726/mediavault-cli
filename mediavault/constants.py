"""Application-wide constants: extensions, junk tokens, regexes, table names.

Kept dependency-free (stdlib only). Consumed by discovery, parsing,
metadata, subtitles, duplicates, and the database layer (§7).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Supported media / subtitle extensions (§3.3, §3.4)
# ---------------------------------------------------------------------------
# FR-311 / FR-315: matched case-insensitively; only these are discovered.
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mkv", ".mp4"})

# §3.4 / FR-603: external subtitle extension (case-insensitive on disk).
SUBTITLE_EXTENSIONS: frozenset[str] = frozenset({".srt"})

# Convenience: extensions without the leading dot, for reporting/filters.
VIDEO_EXTENSIONS_BARE: frozenset[str] = frozenset(
    e.lstrip(".") for e in VIDEO_EXTENSIONS
)


# ---------------------------------------------------------------------------
# Junk-token denylist for movie-title parsing (FR-401)
# ---------------------------------------------------------------------------
# Matched case-insensitively against dot/space-separated tokens. The list
# lives here (not in parsing.py) so it can be extended without touching
# parsing logic, per FR-401.
JUNK_TOKENS: frozenset[str] = frozenset(
    {
        # resolution
        "480p",
        "576p",
        "720p",
        "1080p",
        "1080i",
        "2160p",
        "4k",
        "uhd",
        # source
        "bluray",
        "blu-ray",
        "brrip",
        "bdrip",
        "web-dl",
        "webdl",
        "webrip",
        "web",
        "hdtv",
        "dvdrip",
        "dvd",
        "remux",
        # codecs
        "x264",
        "x265",
        "h264",
        "h265",
        "h.264",
        "h.265",
        "hevc",
        "avc",
        "xvid",
        "divx",
        # audio
        "aac",
        "ac3",
        "dts",
        "ddp",
        "dd",
        "truehd",
        "atmos",
        "5.1",
        "7.1",
        # misc
        "10bit",
        "8bit",
        "hdr",
        "hdr10",
        "dv",
        "proper",
        "repack",
        "extended",
        "unrated",
        "remastered",
        "directors",
        "cut",
    }
)


# ---------------------------------------------------------------------------
# Season-directory pattern (FR-415)
# ---------------------------------------------------------------------------
# Accepts: Season-1 .. Season-9, Season-01 .. Season-09, Season-10 .. Season-NN
# Rejects: Season-0, Season-00, Season-001, Season-010 (zero/redundant padding)
#
# Implemented as a single regex plus a post-match validation for padding,
# because FR-415 distinguishes 1-9 (permissive) from >=10 (unpadded only).
SEASON_DIR_RE: re.Pattern[str] = re.compile(r"^season-(?P<num>\d+)$", re.IGNORECASE)


def parse_season_dir(name: str) -> int | None:
    """Return the season number if *name* is a valid Season-* directory, else None.

    Implements FR-415 exactly:
      * 1-9:   unpadded ("1".."9") or single-zero-padded ("01".."09")
      * >=10:  unpadded only ("10", "11", ...)
      * zero, double-zero, triple-zero, or redundant padding: rejected
    """
    match = SEASON_DIR_RE.match(name)
    if not match:
        return None
    raw = match.group("num")
    number = int(raw)
    if number == 0:
        return None
    if number >= 10:
        # must be unpadded: no leading zero
        return number if raw == str(number) else None
    # 1-9: accept "1".."9" and "01".."09"
    if raw in {str(number), f"0{number}"}:
        return number
    return None


# ---------------------------------------------------------------------------
# Episode-pattern regexes (FR-413)
# ---------------------------------------------------------------------------
# Canonical: Show.Title.S01E02.<rest>.<ext>
EPISODE_SXXEXX_RE: re.Pattern[str] = re.compile(
    r"^(?P<show>.+?)\.S(?P<season>\d{1,3})E(?P<episode>\d{1,4})(?:[.\s].*)?$",
    re.IGNORECASE,
)

# Tolerated: Show.Title.1x02.<rest>.<ext>
EPISODE_1X02_RE: re.Pattern[str] = re.compile(
    r"^(?P<show>.+?)\.(?P<season>\d{1,3})x(?P<episode>\d{1,4})(?:[.\s].*)?$",
    re.IGNORECASE,
)

# Tolerated: Show.Title.Season.1.Episode.2.<rest>.<ext>
EPISODE_LONG_RE: re.Pattern[str] = re.compile(
    r"^(?P<show>.+?)\.Season[.\s](?P<season>\d{1,3})\.Episode[.\s](?P<episode>\d{1,4})(?:[.\s].*)?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Word-separator normalization (FR-402, FR-410)
# ---------------------------------------------------------------------------
# Per FR-402: whitespace, '.', '_', and '-' are word separators; other
# punctuation (apostrophes, etc.) is DROPPED and is NOT a separator.
WORD_SEPARATORS_RE: re.Pattern[str] = re.compile(r"[\s._-]+")
# Everything that is not alphanumeric or a separator is dropped.
NON_WORD_CHARS_RE: re.Pattern[str] = re.compile(r"[^\w\s._-]", re.UNICODE)


# ---------------------------------------------------------------------------
# Table names (FR-803)
# ---------------------------------------------------------------------------
# Centralized so the repository and migrator reference the same strings.
TABLE_SCAN_ROOTS = "scan_roots"
TABLE_SCANS = "scans"
TABLE_SCAN_ROOTS_SCANNED = "scan_roots_scanned"
TABLE_MEDIA_FILES = "media_files"
TABLE_SCAN_MEDIA_FILES = "scan_media_files"
TABLE_MOVIES = "movies"
TABLE_SHOWS = "shows"
TABLE_SEASONS = "seasons"
TABLE_EPISODES = "episodes"
TABLE_SUBTITLES = "subtitles"
TABLE_DUPLICATE_GROUPS = "duplicate_groups"
TABLE_DUPLICATE_MEMBERS = "duplicate_members"
TABLE_META = "meta"


# ---------------------------------------------------------------------------
# Enumerated values used in CHECK constraints (FR-810)
# ---------------------------------------------------------------------------
# Defined here and imported by schema/migrator so Python and SQL agree.
MEDIA_KINDS: tuple[str, ...] = ("movie", "episode")
SCAN_STATUSES: tuple[str, ...] = ("running", "completed", "partial", "failed")
SUBTITLE_KINDS: tuple[str, ...] = ("external", "embedded")
PARSE_STATUSES: tuple[str, ...] = ("ok", "partial", "unparsed")
PARSE_CONFIDENCES: tuple[str, ...] = ("high", "medium", "low")
DUPLICATE_GROUP_KINDS: tuple[str, ...] = ("exact", "near")
ROOT_TYPES: tuple[str, ...] = ("movies", "tv", "auto")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
# FR-603: subtitle base name; §9.1 default.
DEFAULT_SUBS_DIR_NAME = "subs"

# FR-103 / FR-207: "successful" scan statuses.
SUCCESSFUL_SCAN_STATUSES: frozenset[str] = frozenset({"completed", "partial"})
