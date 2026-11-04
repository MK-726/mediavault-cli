# Software Requirements Specification (SRS)

## MediaVault CLI

**Document version:** 1.1\
**Status:** Baseline for v1 implementation\
**Supersedes:** v0.1 (initial draft), v1.0\
**Project type:** Command-line media-library analyzer\
**Target environment:** Linux (Ubuntu first); Python ≥ 3.14\
**Console command:** `mediavault-cli`\
**Project (repo / PyPI) name:** `mediavault-cli`

---

## 1. Introduction

### 1.1 Purpose

MediaVault CLI is a command-line application for scanning, cataloguing, and analyzing a user's locally stored movie and television collection. It produces an organized inventory of media files, extracts descriptive information from filenames and technical information from media files, discovers subtitle files (external and embedded), detects duplicates (exact and near), persists the library in a local SQLite database, and exports reports in TXT, CSV, and Markdown.

This document records the agreed requirements for **v1** and identifies the small number of decisions explicitly deferred to **v1.1** (Google Sheets export) or later. Requirements that were previously open (SRS v0.1, §9) have been resolved; they are now requirements, with their resolution noted.

### 1.2 Project objectives

The application shall:

- Scan one or more user-selected directories (scan roots) containing movie and television collections.
- Discover supported video files (`.mkv`, `.mp4`, case-insensitive).
- Organize discovered files into movies, shows, seasons, and episodes where possible.
- Extract descriptive information from filenames and directory names, distinguishing **parsed** (inferred) from **probed** (read) information.
- Extract technical information from media files via FFprobe, including codec, resolution, duration, audio streams, and **embedded subtitle streams**.
- Match external subtitle files across the layouts described in §4.3, and record embedded subtitle presence.
- Detect **exact duplicates** via staged content hashing and **near-duplicates** via a metadata-derived similarity key.
- Persist library information in a local SQLite database, with each scan as a first-class, identifiable run.
- Provide an interactive menu for all user workflows and a limited set of non-interactive subcommands for scripting.
- Export reports in TXT, CSV, and Markdown.

### 1.3 Intended users

A single individual managing a personal collection of legally obtained movie and television files stored on local disks or external drives on a Linux machine.

### 1.4 Definitions

| Term | Meaning |
|---|---|
| **Scan root** | A filesystem directory the user has registered as a source of media. A library may have multiple scan roots. |
| **Scan run / scan_id** | A single execution of a scan over one or more scan roots, identified by a monotonically increasing integer and persisted. |
| **Media file** | A supported video file: `.mkv` or `.mp4` (case-insensitive). |
| **Movie** | A media file discovered under a **movie root**. |
| **Show** | A first-level subdirectory of a scan root that contains `Season-*` subdirectories or episode files directly. |
| **Season** | A `Season-<n>` subdirectory of a show. |
| **Episode** | A media file whose filename matches the episode pattern (§5.5). |
| **Franchise subdirectory** | A single-level subdirectory under a movie root grouping movies (e.g. `MCU/`, `Star-Wars/`). |
| **Subtitle file** | An external `.srt` file matching a media file, or an embedded subtitle stream inside an `.mkv`. |
| **Discovery** | Locating files on disk without interpreting their names. |
| **Parsing** | Inferring title, year, show, season, and episode from filenames and directory names. |
| **Probed metadata** | Values read directly from the media file via FFprobe. |
| **Parsed metadata** | Values inferred from path or filename. Never authoritative. |
| **Exact duplicate** | Two media files with identical content (same full SHA-256). |
| **Near-duplicate** | Two media files that resolve to the same similarity key (see FR-8xx) but are not exact duplicates. |
| **Similarity key** | For a movie: `(normalized_title, year)`. For an episode: `(show_key, season, episode)`. |

---

## 2. Scope

### 2.1 In scope (v1)

1. Scan roots: registration, listing, removal.
2. Path validation.
3. Movie discovery (recursive, including franchise subdirectories).
4. TV show, season, and episode discovery.
5. Filename and directory parsing for movies and episodes (§5.5).
6. Technical metadata extraction via FFprobe, including embedded subtitle streams.
7. Subtitle discovery and matching across the layouts in §4.3.
8. Exact duplicate detection (staged hashing) and near-duplicate grouping (similarity key).
9. SQLite persistence with first-class scan runs, migrations, and missing-file tracking.
10. Interactive menu covering all eight items in §5.2.
11. Non-interactive subcommands: `scan`, `browse`, `search`, `duplicates`, `analyze`, `export`, `config`, `help`.
12. Reports: TXT, CSV, Markdown.
13. Structured logging to console and rotating file.
14. Configuration via TOML (project-local + XDG) and environment variables.

### 2.2 Out of scope (v1)

- Downloading media or subtitles.
- DRM circumvention.
- Streaming/playback.
- Editing, transcoding, or renaming original files.
- GUI or web application.
- Automatic online metadata retrieval (TMDB, TVDB, etc.).
- **Google Sheets export — deferred to v1.1.**
- Subtitle formats other than external `.srt` and embedded MKV subtitle streams.
- Near-duplicate detection using perceptual or partial-content hashing (v1 uses the metadata similarity key; see FR-7xx).
- Cross-machine library sync.

These may be reconsidered in future versions.

---

## 3. Operating Environment and Constraints

### 3.1 Environment

- Target OS: Linux. Development and initial testing on Ubuntu.
- Language: Python **≥ 3.14**.
- Database: SQLite via the stdlib `sqlite3` module (no ORM).
- Media inspection: **FFprobe** (from the FFmpeg distribution), invoked as a subprocess.
- The application runs as a CLI; no server, no daemon.

### 3.2 Approved third-party dependencies

| Purpose | Library | Used for |
|---|---|---|
| CLI framework | `typer` | Subcommands, flags, `--help`, `--version` |
| Interactive menus / prompts | `questionary` **or** `InquirerPy` | Main menu, multi-choice prompts, confirmations |
| Terminal tables | `rich` | All table output |
| CSV / Markdown export | Python stdlib (`csv`, `pathlib`) | Report files |
| Database | Python stdlib (`sqlite3`) | Persistence |
| Testing | `pytest` (+ `pytest-cov` recommended) | Test suite |
| (v1.1) Google Sheets | `google-api-python-client`, `google-auth` | **Not installed in v1** |

**Responsibility split (binding):**
- **Typer** owns every non-interactive subcommand, every flag, `--help`, and `--version`.
- **questionary / InquirerPy** owns the interactive menu and multi-choice prompts. Typer's own prompt helpers are **not** used for menu navigation or multi-choice input.
- **Rich** owns all tabular and styled output. Neither Typer nor questionary/InquirerPy output is used for tables.

Choose **one** of `questionary` / `InquirerPy` at kickoff; the SRS treats them as interchangeable thereafter.

**Acceptance criterion DEP-01:** each third-party dependency above must be verified to install and import under Python 3.14 before v1 is declared complete.

### 3.3 Supported video formats

- `.mkv`, `.mp4` only.
- Extension matching is case-insensitive (`.MKV`, `.Mp4` recognized).

### 3.4 Supported subtitle formats

- External: `.srt` only.
- Embedded: subtitle streams inside `.mkv`, discovered via FFprobe.

### 3.5 Filesystem constraints

- Media may live on internal or external drives; mount points may differ between scans.
- Nested directory trees are supported.
- The application **never writes inside a scan root** (see NFR-002).
- Symlinks: not followed by default (configurable; see FR-317).
- Hidden files/dirs (`.`-prefixed): skipped by default.
- A configurable list of junk directories is skipped (default in §9.1).

---

## 4. Expected Collection Structure

### 4.1 Movie collections

Movies may live directly under the scan root, in nested directories, or in **franchise subdirectories** (exactly one level deep).

```
Movies/
├── 10.Cloverfield.Lane.2016.1080p.mp4
├── A.Clockwork.Orange.1971.1080p.mkv
├── MCU/
│   ├── Iron.Man.2008.1080p.mkv
│   └── The.Avengers.2012.1080p.mkv
├── Star-Wars/
│   └── Star.Wars.1977.2160p.mkv
├── subs/
│   ├── 10.Cloverfield.Lane.2016.1080p.srt
│   └── A.Clockwork.Orange.1971.1080p.srt
└── MCU/
    └── subs/
        └── Iron.Man.2008.1080p.srt
```

Franchise nesting is exactly **one level** in v1 (FR-310). Deeper nesting is still discovered as ordinary nested directories, and the subtitle ancestor rule (FR-601) still applies.

### 4.2 Television collections

Shows are **first-level subdirectories of a scan root**.

```
TV Shows/
├── Breaking-Bad/                     # multi-season show
│   ├── Season-1/
│   │   ├── Breaking.Bad.S01E01.1080p.mkv
│   │   ├── Breaking.Bad.S01E02.1080p.mkv
│   │   └── subs/
│   │       └── Breaking.Bad.S01E01.1080p.srt
│   └── Season-2/
│       └── Breaking.Bad.S02E01.1080p.mkv
└── Chernobyl/                        # one-season miniseries
    ├── Chernobyl.S01E01.1080p.mkv
    ├── Chernobyl.S01E02.1080p.mkv
    └── subs/
        └── Chernobyl.S01E01.1080p.srt
```

- Season directories are named `Season-<n>` where `<n>` has a leading zero only when the show has more than nine seasons (per user's collection convention): `Season-1` … `Season-9`, then `Season-10` … `Season-20`, etc. `Season-01` is also accepted (FR-415).
- A one-season show may place episodes directly in its show directory (no season subdirectory).
- Per-season `subs/` and per-show `subs/` directories are both supported.

### 4.3 Subtitle layouts (v1)

For a media file `M` with stem `S`, subtitle lookup checks, in order:

1. **Embedded** subtitle streams inside `M` (MKV only).
2. `M.parent / f"{S}.srt"` — same directory as the media file.
3. `M.parent / "subs" / f"{S}.srt"` — season-level or franchise-level `subs/`.
4. For every ancestor `A` of `M.parent` up to and including the scan root: `A / "subs" / f"{S}.srt"` — movie-root and show-root `subs/`.

The first match in the above order is recorded as the matched subtitle. All matches found are recorded (FR-602) but only the first is marked as primary.

### 4.4 Episode filename pattern

The canonical episode filename is:

```
<Show.Title>.S<SS>E<EE>[.<resolution>][.<source>][.<codec>].<ext>
```

Examples:

- `Breaking.Bad.S01E12.1080p.mkv`
- `Chernobyl.S01E01.1080.mkv`
- `Breaking.Bad.S05E12.1080p.mp4`

Additional patterns in §5.5 are accepted for tolerance.

---

## 5. Functional Requirements

Every requirement has a stable ID. All are **v1** unless marked **(v1.1)**.

### 5.1 Scan roots and scan sessions

- **FR-100:** The application shall allow the user to register one or more **scan roots** (directories) and persist them in the database.
- **FR-101:** On Linux, the application shall detect likely mounted volumes (e.g. under `/media`, `/mnt`, `/run/media`) and offer them for selection, in addition to allowing the user to type or paste a path.
- **FR-102:** Each scan run shall be recorded as a first-class entity with an increasing `scan_id`, a start timestamp, an end timestamp, the roots scanned, and per-run counters (`movies_found`, `shows_found`, `episodes_found`, `exact_duplicates_found`, `near_duplicates_found`, `errors_count`).
- **FR-103:** The application shall store the **last successful scan_id** and expose it (FR-1400).
- **FR-104:** The application shall offer a menu action **"Re-scan last roots"** that re-runs a scan over the roots used by the most recent scan, after confirming with the user.
- **FR-105:** Only one scan may run at a time (see NFR-008). A second invocation shall fail with a clear, non-zero exit.

### 5.2 CLI: interactive menu and non-interactive subcommands

- **FR-200:** Running `mediavault-cli` with **no arguments** shall launch an interactive menu.
- **FR-201:** The menu shall present exactly:
  ```
  1. Scan drives and update library
  2. Browse movies
  3. Browse TV shows and episodes
  4. Search and filter media
  5. Find duplicates
  6. Analyze codecs, resolutions, and subtitles
  7. Export reports
  0. Exit
  ```
  Plus: `h`/`?` for help, and a visible footer showing **last scan_id**, **movies**, **shows**, **episodes**, **exact duplicates**, **near duplicates**.
- **FR-202:** The menu shall be rendered by `questionary` / `InquirerPy` and navigable with arrow keys and selectable with Enter.
- **FR-203:** The application shall support the following **non-interactive** subcommands (implemented with Typer):
  - `scan [--root PATH]... [--last]`
  - `browse {movies|shows|episodes} [--show NAME] [--season N]`
  - `search [--title TEXT] [--year N] [--codec NAME] [--min-width N] [--has-subs] [--no-subs] [--has-embedded-subs]`
  - `duplicates {exact|near}`
  - `analyze {codecs|resolutions|subtitles|all}`
  - `export --format {txt,csv,md} [--scope full|movies|show] [--show NAME]`
  - `config {show|init|paths}`
  - `help [COMMAND]`
- **FR-204:** Every subcommand shall support `--help` and `-h` (provided by Typer).
- **FR-205:** The application shall print a `--version` string (provided by Typer).
- **FR-206:** Non-interactive subcommands shall never prompt. If a required argument is missing, they shall exit with code 2 (see FR-207).
- **FR-207:** Exit codes shall follow:
  - `0` — success
  - `1` — runtime error (e.g. database error, FFprobe fatal, export failure)
  - `2` — usage error (bad arguments)
  - `3` — partial scan failure (scan completed but some files could not be inspected; details in log and in scan counters)
- **FR-208:** When `--format json` is not specified, human-readable output shall be printed via `rich` tables. (JSON output is deferred; noted as future extension.)
- **FR-209:** The `analyze` subcommand and menu item 6 shall be **read-only** with respect to the media files and shall not trigger FFprobe; they query the database only.

### 5.3 Path validation

- **FR-300:** The application shall accept a user-provided filesystem path.
- **FR-301:** The application shall determine whether the supplied path exists.
- **FR-302:** When a directory is required, a path to a regular file shall be rejected.
- **FR-303:** When a directory is required, a path to a symlink shall be resolved and re-validated; if the resolved path is a regular file, it shall be rejected.
- **FR-304:** Invalid paths shall produce a clear error message and exit code 2 (non-interactive) or an inline error in the menu.

### 5.4 Discovery

- **FR-310:** The application shall recursively discover `.mkv` and `.mp4` files under a movie scan root, including nested directories and **franchise subdirectories** (one level under the root).
- **FR-311:** Extension matching shall be case-insensitive.
- **FR-312:** Discovered items shall be returned as `pathlib.Path` objects (not bare filenames).
- **FR-313:** The application shall identify **show directories** as first-level subdirectories of a scan root that contain either `Season-*` subdirectories or at least one episode-pattern filename directly.
- **FR-314:** The application shall recursively discover supported video files inside a show directory, both under `Season-*` directories and directly under the show directory.
- **FR-315:** Discovery shall ignore unsupported extensions.
- **FR-316:** A directory whose name ends in `.mkv` or `.mp4` shall not be returned as a media file.
- **FR-317:** By default, symlinks shall **not** be followed. This shall be configurable via `general.follow_symlinks`.
- **FR-318:** Hidden files and directories (`.`-prefixed) shall be skipped by default. Configurable via `general.include_hidden`.
- **FR-319:** Directories whose basename matches any pattern in `general.skip_dirs` shall be skipped (default list in §9.1).
- **FR-320:** Unreadable files or directories shall be reported to the log and skipped; discovery shall not abort because of a single unreadable entry.

### 5.5 Parsing

#### 5.5.1 Movies

- **FR-400:** For each discovered movie file, the application shall attempt to extract a **title** and a **year** from the filename using, in order:
  1. `Title (Year) [junk].ext`
  2. `Title.Year.Resolution.Source.Codec.ext`
  3. `Title.Year.Resolution.ext`
  4. `Title.Year.ext`
- **FR-401:** A **junk-token denylist** shall be applied to strip known non-title tokens: `1080p`, `720p`, `2160p`, `480p`, `BluRay`, `BRRip`, `WEB-DL`, `WEBRip`, `HDTV`, `x264`, `x265`, `H.264`, `HEVC`, `AAC`, `DTS`, `DDP`, `10bit`, etc. The list lives in `mediavault/constants.py` and is extensible.
- **FR-402:** The parsed title shall be normalized for storage and matching (case-folded, trimmed, common punctuation normalized) but the original filename **and** the original-parsed title shall both be preserved.
- **FR-403:** Parsed information shall be stored in `parsed_*` columns, distinct from any future canonical metadata.
- **FR-404:** The original filename and full path shall always be preserved, even if parsing fails entirely.

#### 5.5.2 Television

- **FR-410:** For each discovered episode file, the application shall attempt to extract `(show_key, season, episode)` from the **directory structure first**:
  - Show key from the show directory name, normalized (hyphens/spaces → underscores, lowercased).
  - Season from a `Season-<n>` (or `Season-0<n>`) directory name.
- **FR-411:** If season is not present in a directory name (one-season shows), the season shall be taken from the filename.
- **FR-412:** Episode number shall be taken from the filename.
- **FR-413:** The canonical episode filename pattern is `Show.Title.S<SS>E<EE>.<rest>.<ext>`. Additionally accepted for tolerance: `Show.Title.1x02.<rest>.<ext>` and `Show.Title.Season.1.Episode.2.<rest>.<ext>`.
- **FR-414:** When the show title in the filename disagrees with the show directory name, the **directory name wins**.
- **FR-414a:** When the season number implied by a `Season-<n>` directory disagrees with the `S<SS>` in the filename (e.g. `Season-2/…S01E03…`), the **directory wins**. The filename's season is recorded as a parsing note in the log (debug level).
- **FR-415:** `Season-1` through `Season-9` and `Season-01` through `Season-09` shall be treated as equivalent. `Season-10`+ shall only be accepted in the zero-padded form (`Season-010` is not required; `Season-10` is the canonical form).
- **FR-416:** If the filename yields no episode number but the file is inside a `Season-*` directory, the episode shall be recorded with `episode = NULL` and `parse_status = 'partial'`.
- **FR-417:** Parsed info is stored in `parsed_*` columns; the original path and filename are always preserved.

#### 5.5.3 Shared parsing rules

- **FR-420:** Parsing shall tolerate filenames that do not match any pattern and shall not throw; unmatched files receive `parse_status = 'unparsed'`.
- **FR-421:** Each parsed record shall store `parse_status ∈ {ok, partial, unparsed}` and `parse_confidence ∈ {high, medium, low}` (heuristic).
- **FR-422:** Parsing shall be deterministic and side-effect-free; it shall not touch the filesystem.

### 5.6 Technical metadata (FFprobe)

- **FR-500:** The application shall invoke FFprobe (path from config; default `ffprobe` on `PATH`) for each media file that has not been probed at the current `(size, mtime_ns)` tuple.
- **FR-501:** The following fields shall be extracted when present:
  - `format_name`
  - `duration` (seconds)
  - `bit_rate`
  - video: `codec_name`, `width`, `height`
  - audio: `codec_name`, `channels`, `language` (for the first audio stream; additional streams' summaries stored as JSON in `audio_streams_json`)
  - subtitles: `has_embedded_subs BOOL`, `embedded_sub_count INT`, `embedded_sub_langs TEXT` (comma-separated)
- **FR-502:** `width` and `height` shall be read from the **video stream**, not from `format`. If no video stream exists, `width` and `height` shall be `NULL`.
- **FR-503:** If FFprobe is unavailable or fails for a file, the file's probe fields shall be `NULL`, an error shall be logged at WARNING, and the scan shall continue.
- **FR-504:** A file whose `(size, mtime_ns)` matches its most recent probed values shall **not** be re-probed.
- **FR-505:** The FFprobe invocation shall use JSON output (`-print_format json -show_format -show_streams`).
- **FR-506:** The application shall not fabricate metadata on FFprobe failure. All probe fields shall be `NULL`.
- **FR-507:** When FFprobe is missing at scan start, the application shall warn once and proceed with an empty-metadata scan (probe fields `NULL` for all files); the scan's `errors_count` shall include the missing-FFprobe condition. This is non-fatal.

### 5.7 Subtitle discovery and matching

- **FR-600:** The application shall record whether each media file has **embedded subtitles** (MKV only, via FR-501).
- **FR-601:** For each media file, the application shall search external subtitle files in the order defined in §4.3:
  1. `M.parent / f"{S}.srt"`
  2. `M.parent / "subs" / f"{S}.srt"`
  3. For every ancestor `A` of `M.parent` up to and including the scan root: `A / "subs" / f"{S}.srt"`
- **FR-602:** All matches found shall be recorded in the `subtitles` table; the first match in the order above shall be marked `is_primary = 1`.
- **FR-603:** The `srt` extension shall be matched case-insensitively.
- **FR-604:** Unmatched external subtitle files (`.srt` files under any `subs/` directory that match no media file) shall be recorded in the database as **orphan subtitles** and be listable in reports.
- **FR-605:** The presence of embedded subs **and** an external subtitle file shall both be reported; they are not mutually exclusive.
- **FR-606:** Additional subtitle formats (`.ass`, `.ssa`, `.sub`, `.vtt`) and language suffix parsing (`movie.en.srt`) are **out of scope for v1** and listed in §12.2.

### 5.8 Duplicate detection

#### 5.8.1 Exact duplicates

- **FR-700:** The application shall detect byte-identical media files by full **SHA-256** hash of file contents.
- **FR-701:** Hashing shall be **staged**:
  1. Group candidate files by `(size, extension)`; sizes that appear once are skipped.
  2. For candidate groups, read the **first and last 64 KiB** of each file and compute a partial hash. Files whose partial hash is unique within the group are skipped.
  3. For remaining candidates, compute the full SHA-256.
- **FR-702:** Staged hashing parameters shall be configurable (`duplicates.hash_chunk_bytes`, `duplicates.partial_read_bytes`).
- **FR-703:** Duplicate detection shall never delete, move, or modify files.
- **FR-704:** Each duplicate group shall be recorded with a `group_id`; each file in the group shall reference it.
- **FR-705:** Duplicate results shall be associated with the scan run that produced them (`scan_id`).
- **FR-706:** Hashes for unchanged files (`(size, mtime_ns)` match) shall be reused from the previous scan and not recomputed.

#### 5.8.2 Near-duplicates

- **FR-710:** The application shall compute and store a **similarity key** for each movie and each episode:
  - Movies: `(normalized_parsed_title, parsed_year)` (both lowercased; `year` may be `NULL`, in which case the file is excluded from near-dup grouping).
  - Episodes: `(show_key, season, episode)`.
- **FR-711:** A near-duplicate group is the set of media files in the same similarity key that are **not** all exact duplicates of each other.
- **FR-712:** Near-duplicate results shall be recorded per scan (`scan_id`) and reported as groups with their member paths.
- **FR-713:** Similarity keys shall be stored in a dedicated column (`near_dup_key TEXT`) so that a future perceptual-hash mechanism (v1.1) can co-exist without a schema change.
- **FR-714:** Near-duplicate detection shall be **read-only** with respect to the media files.

### 5.9 Database

- **FR-800:** The application shall use a local SQLite database (stdlib `sqlite3`) at the path from configuration (`general.db_path`; default `~/.local/share/mediavault-cli/mediavault.db`).
- **FR-801:** On connection, the application shall set `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`.
- **FR-802:** The schema shall be versioned using `PRAGMA user_version` and migrated by ordered SQL files in `mediavault/database/migrations/`.
- **FR-803:** The schema shall contain at least these tables (see `docs/schema.md` for DDL):
  - `scan_roots`
  - `scans`
  - `media_files` (one row per discovered file; `path` is the identity in v1; includes `size`, `mtime_ns`, `last_seen_scan_id`, `missing_since_scan_id`, `near_dup_key`, parsed and probed columns)
  - `movies` (view or table referencing `media_files` where `kind='movie'`)
  - `shows`
  - `seasons`
  - `episodes`
  - `subtitles`
  - `duplicate_groups` (kind = `exact` | `near`)
  - `duplicate_members`
- **FR-804:** All SQL access shall be mediated by `mediavault.database.repository`; no module outside `mediavault.database` shall import `sqlite3`.
- **FR-805:** File identity in v1 is the **path**. Renames and moves are treated as delete + add (FR-806).
- **FR-806:** When a file seen in a previous scan is not seen in the current scan, its row shall be marked `missing_since_scan_id = <current scan_id>`. It shall **not** be deleted.
- **FR-807:** When a previously-missing file is seen again, its `missing_since_scan_id` shall be cleared.
- **FR-808:** The database shall retain `parsed_*` and `probed_*` information in separate columns (transparency per NFR-009).
- **FR-809:** The database shall record `ffprobe_version` and `schema_version` in a `meta` table for diagnostics.

### 5.10 Browse and search

- **FR-900:** `browse movies` shall display movies in a `rich` table with columns: title, year, resolution, codec, subtitle (ext/embedded/none), path.
- **FR-901:** `browse shows` shall list shows with episode counts and total season count.
- **FR-902:** `browse episodes [--show NAME] [--season N]` shall list episodes for the given show and optional season.
- **FR-903:** `search` shall support filters: `--title`, `--year`, `--codec`, `--min-width`, `--has-subs`, `--no-subs`, `--has-embedded-subs`. Filters combine with AND.
- **FR-904:** By default, all browse and search results shall **exclude** missing files (`missing_since_scan_id IS NOT NULL`). A `--include-missing` flag shall include them.
- **FR-905:** Results shall be paginated when they exceed one terminal screen; navigation via arrow keys in the menu, or `--page N` in non-interactive mode.

### 5.11 Analysis (menu item 6)

- **FR-1000:** `analyze` shall produce a **read-only**, database-backed report of:
  - Codec distribution (counts per codec, movie vs. episode breakdown).
  - Resolution distribution (counts per `WIDTHxHEIGHT`, movie vs. episode).
  - Subtitle coverage: percentage of files with external subs, with embedded subs, with both, with neither (movie vs. episode).
- **FR-1001:** `analyze` shall not invoke FFprobe or touch the filesystem.
- **FR-1002:** `analyze` shall accept `--scan N` to restrict analysis to files seen in a given scan (default: latest scan).
- **FR-1003:** Output shall be `rich` tables in interactive mode and in non-interactive mode.

### 5.12 Reports and export

- **FR-1100:** `export` shall support `--format {txt,csv,md}` in v1. **Google Sheets is deferred to v1.1.**
- **FR-1101:** `export` shall support `--scope {full,movies,show}` and, when `--scope=show`, a required `--show NAME`.
- **FR-1102:** Movie report columns: `title`, `year`, `resolution`, `codec`, `duration_s`, `has_external_subs`, `has_embedded_subs`, `duplicate_group`, `path`.
- **FR-1103:** Episode report columns: `show`, `season`, `episode`, `resolution`, `codec`, `duration_s`, `has_external_subs`, `has_embedded_subs`, `duplicate_group`, `path`.
- **FR-1104:** A "problem report" section shall list: orphan subtitles, files missing external subtitles, unparsed files, files with probe errors, and missing files.
- **FR-1105:** Reports shall be written under `general.report_output_dir` (default `./reports`), with filenames `<scope>-<timestamp>.<ext>`.
- **FR-1106:** CSV output shall use UTF-8 with a header row and RFC 4180 quoting.
- **FR-1107:** Markdown output shall use tables with a header row per section.
- **FR-1108:** TXT output shall be plain, sectioned, human-readable.
- **FR-1109:** Report generation shall not modify the database.

### 5.13 Configuration and environment

- **FR-1200:** Configuration shall be read from, in precedence order (highest first):
  1. CLI flags
  2. Environment variables (prefix `MEDIAVAULT_CLI_`)
  3. `./config.toml` (project-local)
  4. `~/.config/mediavault-cli/config.toml` (XDG)
  5. Built-in defaults
- **FR-1201:** The configuration file format shall be **TOML**, except for `pytest`, which uses `pytest.ini`.
- **FR-1202:** The configuration schema shall match §9.1.
- **FR-1203:** `mediavault-cli config show` shall print the **resolved** configuration, its source per key, and the database path in use.
- **FR-1204:** `mediavault-cli config init` shall write a default `config.toml` to `./config.toml` if none exists; it shall refuse to overwrite an existing file unless `--force`.
- **FR-1205:** `mediavault-cli config paths` shall print the resolved XDG and project-local config paths, DB path, log dir, and report output dir.
- **FR-1206:** Environment variables shall include `MEDIAVAULT_CLI_DB_PATH`, `MEDIAVAULT_CLI_LOG_DIR`, `MEDIAVAULT_CLI_LOG_LEVEL`, `MEDIAVAULT_CLI_FFPROBE_PATH`, `MEDIAVAULT_CLI_CONFIG`. Other config keys may be overridable by env in v1.1.
- **FR-1207:** Secrets (e.g. Google credentials, in v1.1) shall be accepted **only** from environment variables or a credentials file referenced from env. They shall never be read from the committed TOML.

### 5.14 Logging

- **FR-1300:** The application shall configure a root logger in `logging_setup.configure_logging(level, log_dir, log_filename)`.
- **FR-1301:** Logging shall emit to both a console handler (level = configured `log_level`; INFO by default) and a `RotatingFileHandler` (DEBUG, max 5 MB × 3 backups) at `<log_dir>/mediavault-cli.log`.
- **FR-1302:** During an interactive menu session, the console handler shall use level WARNING to keep the UI readable; the file handler still records DEBUG.
- **FR-1303:** The following events shall be logged at INFO or above:
  - scan start (roots, scan_id)
  - scan end (counters, duration)
  - each FFprobe failure (WARNING, with path and stderr tail)
  - each unreadable file or directory (WARNING)
  - each database migration applied (INFO)
  - each scan aborted due to lock contention (ERROR)
- **FR-1304:** The following shall be logged at DEBUG:
  - each parsed result and its `parse_status`
  - each subtitle match decision (which location matched)
  - each hashing stage entry/exit for a file
- **FR-1305:** Credentials, tokens, and any value from a secret-source env var shall never be logged.
- **FR-1306:** Log records emitted during a scan shall include the `scan_id` in a structured field (via `LoggerAdapter` or contextvar).

### 5.15 Menu footer and status line

- **FR-1400:** The interactive menu shall display, before the options list, a status line populated from the latest successful scan:
  - `Last scan: #<scan_id> at <timestamp>`
  - `Movies: <n>  Shows: <n>  Episodes: <n>  Exact dups: <n>  Near dups: <n>`
- **FR-1401:** If no successful scan exists, the footer shall read `No scans yet — choose 1 to scan.`

---

## 6. Non-Functional Requirements

- **NFR-001 — Data safety:** Scanning, analysis, and reporting shall not modify, rename, move, or delete original media files.
- **NFR-002 — Read-only scan roots:** The application shall never write inside a scan root. Database, logs, reports, and configuration live under XDG or project-local paths.
- **NFR-003 — Robustness:** Empty directories, nested directories, unsupported files, inconsistent filenames, unreadable files, broken symlinks, and missing FFprobe shall be handled without crashing the whole scan.
- **NFR-004 — Error handling:** Per-file errors shall be logged and counted; the scan continues. Fatal errors (invalid root, unwritable DB, missing migrations directory) shall exit non-zero per FR-207 with a clear message.
- **NFR-005 — Maintainability:** Modules shall follow the layout in §7; responsibilities are separated; no module outside `mediavault.database` imports `sqlite3`.
- **NFR-006 — Testability:** Core logic shall be unit-testable without a real media collection. Tests shall use `tmp_path` and mock `subprocess.run` for FFprobe. A small set of integration tests marked `@pytest.mark.integration` may require real `ffprobe`.
- **NFR-007 — Portability:** All path handling shall use `pathlib`. No hard-coded absolute paths.
- **NFR-008 — Single writer:** Concurrent scans shall be prevented by an exclusive lock file (`<db_dir>/.scan.lock`). A second scan invocation shall exit non-zero with a clear message.
- **NFR-009 — Transparency:** Parsed and probed information shall be stored in distinct columns and reported distinctly.
- **NFR-010 — Performance:** Staged hashing (FR-701) and probe reuse for unchanged files (FR-504) shall be applied. A scan shall process files sequentially in v1; parallelism is deferred.
- **NFR-011 — Security:** Secrets shall come only from env or env-referenced files. Logs shall never include secret values.
- **NFR-012 — Observability:** A rotating log file, per-scan counters, and `scan_id` in log records together shall allow post-hoc diagnosis of any scan.
- **NFR-013 — Python version compatibility:** Every third-party dependency shall be verified against Python 3.14 before v1 sign-off (DEP-01).
- **NFR-014 — Reproducibility:** `pytest` shall be runnable via a single command (`pytest`) with no manual setup beyond installing the package in editable mode.

---

## 7. Software Architecture

```
mediavault-cli/
├── mediavault/
│   ├── __init__.py
│   ├── __main__.py              # `python -m mediavault`
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py              # Typer app + entrypoint + `__main__` hook
│   │   ├── menu.py              # interactive menu (questionary/InquirerPy)
│   │   ├── prompts.py           # confirmations, path pickers
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── scan.py
│   │       ├── browse.py
│   │       ├── search.py
│   │       ├── duplicates.py
│   │       ├── analyze.py
│   │       ├── export.py
│   │       ├── config_cmd.py
│   │       └── help.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py            # precedence resolution
│   │   ├── defaults.py          # built-in defaults
│   │   └── schema.py            # dataclass/TypedDict of resolved config
│   ├── constants.py             # extensions, regexes, junk tokens, table names
│   ├── errors.py                # MediaVaultError hierarchy
│   ├── models.py                # dataclasses: ScanRun, Movie, Show, Episode, Subtitle, DuplicateGroup
│   ├── logging_setup.py
│   ├── paths.py
│   ├── discovery.py
│   ├── parsing.py
│   ├── metadata.py
│   ├── subtitles.py
│   ├── duplicates.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── schema.py
│   │   ├── migrations.py
│   │   ├── migrations/
│   │   │   └── 0001_init.sql
│   │   └── repository.py
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── base.py              # Report protocol
│   │   ├── txt.py
│   │   ├── csv_report.py        # NOT csv.py (avoid stdlib shadow)
│   │   ├── markdown.py
│   │   └── (google_sheets.py — v1.1)
│   └── utils.py
├── tests/
│   ├── conftest.py              # tmp-library fixture, in-memory DB, fake ffprobe
│   ├── fixtures/                # tiny fake ffprobe JSON, sample filenames
│   ├── test_cli/
│   │   ├── test_menu.py
│   │   └── test_commands.py
│   ├── test_paths.py
│   ├── test_discovery.py
│   ├── test_parsing.py
│   ├── test_metadata.py
│   ├── test_subtitles.py
│   ├── test_duplicates.py
│   ├── test_reports.py
│   └── database/
│       ├── test_connection.py
│       ├── test_schema.py
│       └── test_repository.py
├── docs/
│   ├── SRS.md                   # this document
│   ├── schema.md                # DDL + ERD description
│   ├── config.example.toml
│   └── logging.md
├── scripts/
│   └── dev.sh                   # lint, typecheck, test
├── README.md
├── CHANGELOG.md
├── LICENSE                      # [OPEN-Q] choose at kickoff
├── pyproject.toml
├── pytest.ini
├── .env.example
├── .gitignore
└── .pre-commit-config.yaml
```

**Rule:** Empty placeholder modules are not created. A module exists because it implements functionality covered by a requirement.

---

## 8. Data Model (summary; DDL in `docs/schema.md`)

**Entities** (fields abbreviated):

- **`scan_roots(id, path, added_at, last_scan_id)`**
- **`scans(id, started_at, ended_at, status, movies_found, shows_found, episodes_found, exact_dups, near_dups, errors_count)`**
- **`media_files(id, path UNIQUE, filename, extension, kind, size, mtime_ns, last_seen_scan_id, missing_since_scan_id, parsed_title, parsed_year, parse_status, show_key, season, episode, near_dup_key, codec, width, height, duration, bit_rate, audio_codec, audio_channels, audio_streams_json, has_embedded_subs, embedded_sub_count, embedded_sub_langs, probed_at, ffprobe_version)`**
- **`movies(id, media_file_id UNIQUE, title, year, franchise)`**
- **`shows(id, show_key UNIQUE, display_name)`**
- **`seasons(id, show_id, number)`**
- **`episodes(id, media_file_id UNIQUE, show_id, season_id, episode_number)`**
- **`subtitles(id, media_file_id, path, kind, is_primary, missing_since_scan_id)`**
- **`duplicate_groups(id, scan_id, kind)`**
- **`duplicate_members(group_id, media_file_id, hash_value)`**
- **`meta(key, value)`** — `schema_version`, `ffprobe_version`, `last_successful_scan_id`

File identity in v1 is `media_files.path` (FR-805).

---

## 9. Configuration and Environment Variables

### 9.1 TOML schema (see `docs/config.example.toml`)

```toml
[general]
db_path              = "~/.local/share/mediavault-cli/mediavault.db"
log_dir              = "~/.local/state/mediavault-cli/logs"
log_level            = "INFO"                 # DEBUG | INFO | WARNING | ERROR
ffprobe_path         = "ffprobe"
subs_dir_name        = "subs"
report_output_dir    = "./reports"
probe_skip_unchanged = true
follow_symlinks      = false
include_hidden       = false
skip_dirs            = ["@eaDir", "#recycle", ".Trash-*", "$RECYCLE.BIN", "System Volume Information"]

[scan]
default_roots = []

[duplicates]
hash_chunk_bytes   = 65536
partial_read_bytes = 1048576

# v1.1:
# [google]
# credentials_file = ""
# sheet_id         = ""
```

### 9.2 Environment variables

| Variable | Maps to | Notes |
|---|---|---|
| `MEDIAVAULT_CLI_CONFIG` | Path to project-local config | Overrides `./config.toml` |
| `MEDIAVAULT_CLI_DB_PATH` | `general.db_path` | |
| `MEDIAVAULT_CLI_LOG_DIR` | `general.log_dir` | |
| `MEDIAVAULT_CLI_LOG_LEVEL` | `general.log_level` | |
| `MEDIAVAULT_CLI_FFPROBE_PATH` | `general.ffprobe_path` | |

Precedence (FR-1200): CLI flags > env > `./config.toml` > XDG `config.toml` > defaults.

---

## 10. Testing and Acceptance Criteria

Tests are written with `pytest`. `conftest.py` provides:

- `tmp_library` — creates a temporary directory tree matching §4.
- `memory_db` — an in-memory SQLite database with migrations applied.
- `fake_ffprobe` — a fixture that monkeypatches `subprocess.run` to return canned FFprobe JSON.
- `sample_paths` — filename corpus from §4.1, §4.2, §4.4, including edge cases.

Acceptance criteria (one per FR block, abbreviated; the full set lives alongside the tests):

- **Discovery (FR-310–320):** nested `.mkv`/`.mp4` found; uppercase extensions found; unsupported ignored; dir named `x.mkv` not returned; empty dir → empty result; symlinks/hidden/junk-dirs respected; unreadable subdir does not abort.
- **Parsing (FR-400–422):** four movie patterns parse; junk denylist strips tokens; `Breaking.Bad.S05E12.1080p.mp4` → `show_key=breaking_bad`, `season=5`, `episode=12`; `Season-01/…S01E02` resolves season 1 from both dir and file; **`Season-2/…S01E03…` resolves season 2 from the directory** (FR-414a; directory wins).
- **Metadata (FR-500–507):** parse canned FFprobe JSON; missing video stream → width/height NULL; embedded subs counted; unchanged `(size, mtime_ns)` not re-probed; FFprobe failure → all probe fields NULL.
- **Subtitles (FR-600–606):** all five layouts from §4.3 matched; orphan `.srt` recorded; embedded-only media recorded as having subs.
- **Duplicates (FR-700–714):** staged hashing groups identical files; single-size files skipped; near-dup key groups different-resolution copies of the same title.
- **Database (FR-800–809):** migrations apply from empty; re-scan marks missing files; returning files clear `missing_since_scan_id`; `PRAGMA user_version` matches `schema_version`.
- **Search / browse (FR-900–905):** filters AND-combine; missing files excluded by default, included with `--include-missing`.
- **Reports (FR-1100–1109):** TXT/CSV/MD produced with required columns; orphan-subtitles section present.
- **CLI / menu (FR-200–209):** each subcommand supports `--help`; exit codes 0/1/2/3 observed; menu launches and exits.
- **Config (FR-1200–1207):** precedence order observed; `config show` prints sources; `config init --force` overwrites, otherwise refuses.

---

## 11. Development Milestones

1. Scaffold repo per §7; `pyproject.toml`, `pytest.ini`, `.env.example`, `.gitignore`, pre-commit; verify all deps install on Python 3.14 (DEP-01).
2. `errors.py`, `constants.py`, `models.py`, `logging_setup.py`.
3. `paths.py` + `discovery.py` + tests.
4. `parsing.py` + tests (movie + episode patterns).
5. `database/` (connection, migrations, schema 0001, repository) + tests.
6. `metadata.py` (with mocked FFprobe) + tests.
7. `subtitles.py` + tests.
8. `duplicates.py` (exact + near) + tests.
9. `reports/` (txt, csv, md) + tests.
10. `cli/` (Typer app, subcommands, menu, prompts) + tests.
11. End-to-end smoke test on a small synthetic library.
12. Docs polish: `docs/schema.md`, `docs/logging.md`, `README.md`.

---

## 12. Open Questions and Deferred Decisions

### 12.1 Resolved from SRS v0.1 (for the record)

All ten open questions from v0.1 have been resolved during specification and are now requirements in §5. No follow-ups remain from v0.1.

### 12.2 Deferred to v1.1 or later

1. **Google Sheets export** — deferred to v1.1. Auth mechanism (service account vs. OAuth) to be decided then.
2. **Additional subtitle formats** — `.ass`, `.ssa`, `.sub`, `.vtt`.
3. **Subtitle language suffixes** — `movie.en.srt`, `movie.en.forced.srt`; and language-aware "primary" selection.
4. **Parallel FFprobe** — `--jobs N`.
5. **JSON output** for non-interactive subcommands.
6. **Perceptual-hash near-duplicate detection** — schema column `near_dup_key` already exists, so this is additive.
7. **Move/rename detection** — v1 treats renames as delete + add.
8. **Online metadata retrieval** — TMDB/TVDB lookup, canonical titles, canonical IDs.
9. **License** — must be chosen before the first public commit.

### 12.3 Residual ambiguities (explicitly flagged for v1 sign-off)

- **`[OPEN-Q-1]` Near-dup key normalization.** `normalized_parsed_title` for movies: confirm `lower() + strip non-alphanumerics + collapse whitespace`. Assumed yes; will be enforced in `parsing.py` with a test.
- **`[OPEN-Q-2]` Show key normalization.** `show_key` for `Breaking-Bad` → `breaking_bad`. Assumed; same normalization as above but preserves underscores. Confirm.
- **`[OPEN-Q-3]` Orphan subtitle scope.** Should orphan `.srt` detection scan **only** `subs/` directories (any depth), or every `.srt` under a scan root? Assumed: any `.srt` under a scan root that matches no media file. Confirm.

---

## 13. Change Management

This specification is version 1.1. Changes follow:

- Update the affected requirement(s) in place.
- Keep requirement identifiers stable; deprecated requirements are marked `[DEPRECATED]` rather than renumbered.
- Add tests for any newly defined behavior.
- New open questions are added to §12.3 with an ID (`[OPEN-Q-n]`) and closed only by promoting to a requirement.
- Version bumps: **minor** for requirements added/changed, **patch** for wording, **major** for scope removal or an incompatible schema decision.

---

## Appendix A — Resolved decisions from the specification dialogue (traceability)

| Decision | Answer | Where it lives |
|---|---|---|
| CLI modes | Menu + non-interactive subcommands + `--help` | FR-200–FR-209 |
| CLI framework | Typer (subcommands/flags), questionary/InquirerPy (menu), Rich (tables) | §3.2, §7 |
| Drive detection | Linux volume detection + manual path entry | FR-101 |
| Multiple scan roots | Yes | FR-100, FR-805 |
| Exit codes | Conventional 0/1/2/3 | FR-207 |
| Scan runs as first-class | Yes, `scan_id` | FR-102 |
| File identity | Path (renames = delete+add) | FR-805 |
| Stale files | Marked missing, not deleted | FR-806 |
| Hashing strategy | Staged (size → partial → full SHA-256) | FR-701 |
| DB layer | stdlib `sqlite3`, repository-mediated | FR-800, FR-804 |
| Google Sheets | Deferred to v1.1 | FR-1100, §12.2 |
| Python floor | 3.14 | §3.1, NFR-013 |
| Console command | `mediavault-cli` | front matter, FR-200 |
| Dependency policy | Typer + Rich + questionary/InquirerPy + stdlib + pytest (+ Google libs in v1.1) | §3.2 |
| Config format | TOML (pytest uses INI) | FR-1201 |
| Config precedence | CLI > env > `./config.toml` > XDG > defaults | FR-1200 |
| Subtitle layouts | Ancestor `subs/` rule + embedded | FR-601, §4.3 |
| Movie patterns | Four patterns + junk denylist | FR-400–FR-401 |
| Episode pattern | `Show.Title.SxxEyy…` + tolerated variants | FR-413 |
| Season zero-padding | `Season-1`…`Season-9`, `Season-10`+; `Season-01` accepted | FR-415 |
| Show title authority | Directory wins, filename is fallback | FR-414 |
| **Season conflict** | **Directory wins** | **FR-414a** |
| FFprobe fields | Format + video + audio + embedded subs + dims | FR-501–FR-502 |
| Probe reuse | Skip unchanged `(size, mtime_ns)` | FR-504 |
| Duplicate scope | Exact (byte-identical) **and** near (similarity key) | FR-700–FR-714 |
| Near-dup key | Metadata-derived (title+year / show+season+episode) | FR-710 |
| Report scope | Full library in v1; `--movies` and `--show` filters | FR-1101 |
| Symlinks / hidden / junk | Not followed / skipped / denylist | FR-317–FR-319 |
| Single writer | Lock file | NFR-008 |
| Scan roots read-only | Never write inside | NFR-002 |

---

**End of SRS v1.1.**