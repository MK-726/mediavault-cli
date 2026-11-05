**Answer recorded: Q34 → 34A.** All decisions are now locked. Here is the complete decision log I'll apply, followed by the revised SRS.

---

## Decision log (all 34 questions)

| # | Topic | Decision |
|---|---|---|
| 1 | Scan root classification | 1A — `root_type ∈ {movies, tv, auto}` |
| 2 | Historical scan membership | 2A — `scan_media_files` join table; snapshots deferred (§12.2) |
| 3 | `auto` behavior | 3A — both passes + per-file precedence |
| 4 | Exact-dup candidate grouping | 4A — group by `size` only |
| 5 | Partial-hash config | 5A — `hash_chunk_bytes` + `partial_hash_bytes`; small files read whole |
| 6 | Migration module naming | 6A — `migrator.py` + `migrations/` |
| 7 | Report output dir | 7A — XDG default; reject paths inside scan root |
| 8 | Near-dup grouping | 8A — ≥2 distinct hashes; include all; annotate |
| 9 | Embedded subtitles | 9A — `kind ∈ {external, embedded}`, nullable path, summary row |
| 10 | Subtitle stem matching | 10A — case-insensitive stem+ext; record all; lexicographic primary |
| 11 | Season dir rules | 11A — permissive 1–9, unpadded ≥10, reject zero/triple-zero |
| 12 | Discovery overlap / extras | 12A — skip `Season-*` under movies root; TV = pattern-or-season-dir, else unparsed episode |
| 13 | FFprobe cache identity | 13A — `(size, mtime_ns, ffprobe_version)`; retry failures; timeout config |
| 14 | Config file selection | 14A — `MEDIAVAULT_CLI_CONFIG` replaces `./config.toml`; invalid → exit 1 |
| 15 | Scan lock | 15A — `fcntl.flock`; no PID checks |
| 16 | Scan status vocabulary | 16A — `running/completed/partial/failed`; successful = completed\|partial |
| 17 | `scan` flags | 17A — repeatable `--root`; `--root`/`--last` exclusive; no-flag → scan all registered |
| 18 | Search filters | 18A — explicit subs semantics; add show/season/episode/resolution/duration; reject conflicts |
| 19 | Service layer | 19A — all four service modules + import-boundary rule |
| 20 | `movies`/`episodes` duplication | 20A — link-table only; canonical deferred |
| 21 | DB constraints/indexes | 21A — FKs, NOT NULL, CHECK, UNIQUE, indexes |
| 22 | FR-208 / Appendix A | 22A — JSON out of scope; align Appendix A to `--scope` |
| 23 | Logging namespace & counters | 23A — `"mediavault"` logger; per-category error counters |
| 24 | FFprobe failure handling | 24A — timeout+kill, stderr truncation, no retry |
| 25 | Filesystem edge cases | 25A — overlap, unmounted-root protection, unstable files, symlink cycles |
| 26 | Migration rules | 26A — immutability, future-version refusal, per-migration tx |
| 27 | `utils.py` policy | 27A — keep with binding placement rule |
| 28 | Missing FFprobe | 28A — `partial`, embedded NULL, hashing+ext-subs still run |
| 29 | Packaging entry point | 29A — `mediavault-cli = "mediavault.cli.main:app"` |
| 30 | Menu behavior | 30A — inline drive/path, graceful no-prior-scan, services-only |
| 31 | Test additions | 31A — integration + discovery edge + config precedence scenarios |
| 32 | Milestone order | 32A — 17-phase order, menu last |
| 33 | Residual ambiguities | 33D — movies: display title-only whitespace+title-case, key underscore+lower; shows: display whitespace+title-case, key underscore+lower; P punctuation; Q-3 as recommended |
| 34 | Version | 34A — v1.2, minor, revision history |

I'll now produce the full revised SRS v1.2. Given its length, I'll write it as one complete document.

---

# Software Requirements Specification (SRS)

## MediaVault CLI

**Document version:** 1.2\
**Status:** Baseline for v1 implementation (revised — pre-implementation)\
**Supersedes:** v0.1 (initial draft), v1.0, v1.1\
**Project type:** Command-line media-library analyzer\
**Target environment:** Linux (Ubuntu first); Python ≥ 3.14\
**Console command:** `mediavault-cli`\
**Project (repo / PyPI) name:** `mediavault-cli`

---

## Revision history

| Version | Date | Summary |
|---|---|---|
| 0.1 | — | Initial draft |
| 1.0 | — | First structured baseline |
| 1.1 | — | Baseline for v1 implementation |
| 1.2 | — | Review-driven revision. Added scan-root classification, historical scan membership, scan status vocabulary, per-category error counters, service layer, DB constraints/indexes, migration rules, FFprobe cache/timeout/failure semantics, subtitle representation and case-matching rules, season-directory rules, discovery edge-case rules, config-file selection rule, lock semantics, search-filter semantics, packaging entry point, menu behavior, expanded tests, reordered milestones, revised normalization. See §13.1. |

**Note:** No v1 database has been shipped. The schema changes in v1.2 are pre-implementation refinements, not real-world migrations.

---

## 1. Introduction

### 1.1 Purpose

MediaVault CLI is a command-line application for scanning, cataloguing, and analyzing a user's locally stored movie and television collection. It produces an organized inventory of media files, extracts descriptive information from filenames and technical information from media files, discovers subtitle files (external and embedded), detects duplicates (exact and near), persists the library in a local SQLite database, and exports reports in TXT, CSV, and Markdown.

This document records the agreed requirements for **v1** and identifies the small number of decisions explicitly deferred to **v1.1** (Google Sheets export) or later. Requirements that were previously open (SRS v0.1, §9) have been resolved; they are now requirements, with their resolution noted. Decisions introduced by the v1.1 review are incorporated throughout and summarised in §13.1.

### 1.2 Project objectives

The application shall:

- Scan one or more user-selected directories (scan roots) containing movie and television collections.
- Classify each scan root as a movie root, a TV root, or an auto-detected root (FR-100, FR-105).
- Discover supported video files (`.mkv`, `.mp4`, case-insensitive).
- Organize discovered files into movies, shows, seasons, and episodes where possible.
- Extract descriptive information from filenames and directory names, distinguishing **parsed** (inferred) from **probed** (read) information.
- Extract technical information from media files via FFprobe, including codec, resolution, duration, audio streams, and **embedded subtitle streams**.
- Match external subtitle files across the layouts described in §4.3, and record embedded subtitle presence.
- Detect **exact duplicates** via staged content hashing and **near-duplicates** via a metadata-derived similarity key.
- Persist library information in a local SQLite database, with each scan as a first-class, identifiable run and with per-scan file membership.
- Provide an interactive menu for all user workflows and a limited set of non-interactive subcommands for scripting.
- Export reports in TXT, CSV, and Markdown.

### 1.3 Intended users

A single individual managing a personal collection of legally obtained movie and television files stored on local disks or external drives on a Linux machine.

### 1.4 Definitions

| Term | Meaning |
|---|---|
| **Scan root** | A filesystem directory the user has registered as a source of media. A library may have multiple scan roots. Each root has a **root type** (`movies`, `tv`, `auto`). |
| **Root type** | Classification of a scan root that determines discovery behavior (FR-105). |
| **Scan run / scan_id** | A single execution of a scan over one or more scan roots, identified by a monotonically increasing integer and persisted. |
| **Scan membership** | The record, in `scan_media_files`, that a given media file was discovered in a given scan. |
| **Media file** | A supported video file: `.mkv` or `.mp4` (case-insensitive). |
| **Movie** | A media file discovered under a **movies** root (or classified as a movie by an `auto` root). |
| **Show** | A first-level subdirectory of a **tv** root that contains `Season-*` subdirectories or episode files directly. |
| **Season** | A `Season-<n>` subdirectory of a show. |
| **Episode** | A media file whose filename matches the episode pattern (§5.5.2) or that resides inside a `Season-*` directory. |
| **Franchise subdirectory** | A single-level subdirectory under a movies root grouping movies (e.g. `MCU/`, `Star-Wars/`). |
| **Subtitle file** | An external `.srt` file matching a media file, or an embedded subtitle stream inside an `.mkv`. |
| **Discovery** | Locating files on disk without interpreting their names. |
| **Parsing** | Inferring title, year, show, season, and episode from filenames and directory names. |
| **Probed metadata** | Values read directly from the media file via FFprobe. |
| **Parsed metadata** | Values inferred from path or filename. Never authoritative. |
| **Exact duplicate** | Two media files with identical content (same full SHA-256), irrespective of name or extension. |
| **Near-duplicate** | Two media files that share a similarity key and differ in content (see FR-710–FR-712). |
| **Similarity key** | For a movie: `(normalized_title_key, year)`. For an episode: `(show_key, season, episode)`. |
| **Display title** | Human-readable normalized title: whitespace-separated, title-case, title only (year separate). |
| **Match key** | Equality form: lowercased, underscore-separated (FR-402, FR-410). |

---

## 2. Scope

### 2.1 In scope (v1)

1. Scan roots: registration (with root type), listing, removal.
2. Path validation.
3. Movie discovery (recursive, including franchise subdirectories) driven by root type.
4. TV show, season, and episode discovery driven by root type.
5. Filename and directory parsing for movies and episodes (§5.5).
6. Technical metadata extraction via FFprobe, including embedded subtitle streams.
7. Subtitle discovery and matching across the layouts in §4.3.
8. Exact duplicate detection (staged hashing) and near-duplicate grouping (similarity key).
9. SQLite persistence with first-class scan runs, per-scan membership, migrations, constraints, indexes, and missing-file tracking.
10. Interactive menu covering all eight items in §5.2.
11. Non-interactive subcommands: `scan`, `browse`, `search`, `duplicates`, `analyze`, `export`, `config`, `help`.
12. Reports: TXT, CSV, Markdown.
13. Structured logging to console and rotating file.
14. Configuration via TOML (project-local + XDG) and environment variables.
15. An application/service layer separating orchestration from the CLI.

### 2.2 Out of scope (v1)

- Downloading media or subtitles.
- DRM circumvention.
- Streaming/playback.
- Editing, transcoding, or renaming original files.
- GUI or web application.
- Automatic online metadata retrieval (TMDB, TVDB, etc.).
- **Google Sheets export — deferred to v1.1.**
- Subtitle formats other than external `.srt` and embedded MKV subtitle streams.
- Near-duplicate detection using perceptual or partial-content hashing (v1 uses the metadata similarity key; see FR-710–FR-714).
- Cross-machine library sync.
- **Per-scan metadata snapshots** — deferred (see §12.2); v1 records membership only.
- **JSON output** for non-interactive subcommands.

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
- The application **never writes inside a scan root** (see NFR-002; enforced for exports by FR-1110).
- Symlinks: not followed by default (configurable; see FR-317). Symlink cycles shall not cause infinite traversal (FR-324).
- Hidden files/dirs (`.`-prefixed): skipped by default.
- A configurable list of junk directories is skipped (default in §9.1).
- Overlapping scan roots are canonicalized and de-duplicated at scan time (FR-321).

---

## 4. Expected Collection Structure

### 4.1 Movie collections

Movies may live directly under a **movies** root, in nested directories, or in **franchise subdirectories** (exactly one level deep).

```
Movies/                                # registered as root_type = movies
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

A video file inside a `Season-*` directory under a **movies** root is **not** classified as a movie; it is skipped with a DEBUG log (FR-312).

### 4.2 Television collections

Shows are **first-level subdirectories of a tv root**.

```
TV Shows/                              # registered as root_type = tv
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

- Season directories follow FR-415 (permissive for 1–9, unpadded for 10+, zero-padding rejected).
- A one-season show may place episodes directly in its show directory (no season subdirectory).
- Per-season `subs/` and per-show `subs/` directories are both supported.
- A video file inside a show directory that matches neither the episode pattern nor a `Season-*` location is recorded as `kind='episode'`, `parse_status='unparsed'` (FR-314).

### 4.3 Subtitle layouts (v1)

For a media file `M` with stem `S`, subtitle lookup checks, in order:

1. **Embedded** subtitle streams inside `M` (MKV only; recorded as `kind='embedded'`).
2. `M.parent / f"{S}.srt"` — same directory as the media file.
3. `M.parent / "subs" / f"{S}.srt"` — season-level or franchise-level `subs/`.
4. For every ancestor `A` of `M.parent` up to and including the scan root: `A / "subs" / f"{S}.srt"` — movie-root and show-root `subs/`.

External matching is case-insensitive for both the stem and the `.srt` extension (FR-603). All external matches found are recorded (FR-602); the first in the order above is `is_primary = 1`.

### 4.4 Episode filename pattern

The canonical episode filename is:

```
<Show.Title>.S<SS>E<EE>[.<resolution>][.<source>][.<codec>].<ext>
```

Examples:

- `Breaking.Bad.S01E12.1080p.mkv`
- `Chernobyl.S01E01.1080.mkv`
- `Breaking.Bad.S05E12.1080p.mp4`

Additional patterns in §5.5.2 are accepted for tolerance.

---

## 5. Functional Requirements

Every requirement has a stable ID. All are **v1** unless marked **(v1.1)**.

### 5.1 Scan roots and scan sessions

- **FR-100:** The application shall allow the user to register one or more **scan roots** (directories) with an explicit **root type** (`movies`, `tv`, or `auto`) and persist them in the database.
- **FR-101:** On Linux, the application shall detect likely mounted volumes (e.g. under `/media`, `/mnt`, `/run/media`) and offer them for selection, in addition to allowing the user to type or paste a path.
- **FR-102:** Each scan run shall be recorded as a first-class entity with an increasing `scan_id`, a start timestamp, an end timestamp, the roots scanned, a `status`, and per-run counters (`movies_found`, `shows_found`, `episodes_found`, `exact_duplicates_found`, `near_duplicates_found`, `filesystem_errors`, `probe_errors`, `hash_errors`, `errors_count`).
  - `errors_count` is the aggregate of `filesystem_errors + probe_errors + hash_errors`.
  - `status ∈ {running, completed, partial, failed}` and is constrained by `CHECK` (§5.9).
- **FR-102a:** For each scan, the application shall record **scan membership** in `scan_media_files` (`scan_id`, `media_file_id`, `discovered_at`, `scan_status`) for every media file discovered in that scan. This is the authoritative historical record; `media_files.last_seen_scan_id` is a denormalized fast-access field.
- **FR-103:** The application shall store the **last successful scan_id** and expose it (FR-1400). A scan is *successful* when its `status` is `completed` or `partial`; a `failed` scan shall never update the last-successful value.
- **FR-104:** The application shall offer a menu action **"Re-scan last roots"** that re-runs a scan over the roots used by the most recent scan, after confirming with the user. When no prior scan exists, the menu shall display a friendly message and return to the menu (FR-201).
- **FR-105:** Discovery behavior shall be driven by `root_type`:
  - `movies`: recursive movie discovery (FR-310–FR-312).
  - `tv`: show/season/episode discovery (FR-313–FR-314).
  - `auto`: both passes, with per-file classification resolved by the precedence rule in FR-105a.
- **FR-105a (auto classification):** Under an `auto` root, each media file shall be classified **exactly once**. Precedence: if the file is inside a `Season-*` directory **or** its filename matches an episode pattern, it is an episode; otherwise it is a movie. A file shall never be double-counted. Non-obvious classifications shall be logged at DEBUG.
- **FR-105b:** Concurrent scans shall be prevented (NFR-008). A second invocation shall fail with a clear, non-zero exit.
- **FR-105c:** At scan start, any pre-existing scan row left in `status='running'` (from a crashed process) shall be marked `failed` before the new scan begins.

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
  - Menu item 1, when no roots are registered, shall present detected volumes (FR-101) and a "enter a path" option; on selection it registers the root (prompting for `root_type`) and proceeds. When roots exist, it shall offer "scan all registered" / "re-scan last roots" / "add a root".
- **FR-202:** The menu shall be rendered by `questionary` / `InquirerPy` and navigable with arrow keys and selectable with Enter.
- **FR-203:** The application shall support the following **non-interactive** subcommands (implemented with Typer):
  - `scan [--root PATH]... [--last]`
  - `browse {movies|shows|episodes} [--show NAME] [--season N]`
  - `search [--title TEXT] [--year N] [--codec NAME] [--min-width N] [--show NAME] [--season N] [--episode N] [--resolution WxH] [--min-duration S] [--max-duration S] [--has-subs] [--has-external-subs] [--no-subs] [--has-embedded-subs] [--include-missing]`
  - `duplicates {exact|near}`
  - `analyze {codecs|resolutions|subtitles|all} [--scan N]`
  - `export --format {txt,csv,md} [--scope full|movies|show] [--show NAME]`
  - `config {show|init|paths}`
  - `help [COMMAND]`
- **FR-203a:** For `scan`, `--root` shall be **repeatable**. `--root` and `--last` shall be **mutually exclusive** (usage error, exit 2). With neither flag: if registered roots exist, scan all of them; if none exist, exit 2.
- **FR-204:** Every subcommand shall support `--help` and `-h` (provided by Typer).
- **FR-205:** The application shall print a `--version` string (provided by Typer).
- **FR-206:** Non-interactive subcommands shall never prompt. If a required argument is missing, they shall exit with code 2 (see FR-207).
- **FR-207:** Exit codes shall follow:
  - `0` — success (scan `completed`)
  - `1` — runtime error (e.g. database error, FFprobe fatal, export failure, configuration error, lock contention)
  - `2` — usage error (bad arguments)
  - `3` — partial scan failure (scan `partial`: completed but some files could not be inspected; details in log and in scan counters)
- **FR-208:** All non-interactive subcommands shall produce human-readable output using Rich tables. Machine-readable JSON output is out of scope for v1 (see §12.2).
- **FR-209:** The `analyze` subcommand and menu item 6 shall be **read-only** with respect to the media files and shall not trigger FFprobe; they query the database only.

### 5.3 Path validation

- **FR-300:** The application shall accept a user-provided filesystem path.
- **FR-301:** The application shall determine whether the supplied path exists.
- **FR-302:** When a directory is required, a path to a regular file shall be rejected.
- **FR-303:** When a directory is required, a path to a symlink shall be resolved and re-validated; if the resolved path is a regular file, it shall be rejected.
- **FR-304:** Invalid paths shall produce a clear error message and exit code 2 (non-interactive) or an inline error in the menu.

### 5.4 Discovery

- **FR-310:** Under a **movies** root, the application shall recursively discover `.mkv` and `.mp4` files, including nested directories and **franchise subdirectories** (one level under the root).
- **FR-311:** Extension matching shall be case-insensitive.
- **FR-312:** Under a **movies** root, a video file located inside a `Season-*` directory shall **not** be classified as a movie; it shall be skipped with a DEBUG log. (Season directories are a TV construct.)
- **FR-313:** Under a **tv** root, the application shall identify **show directories** as first-level subdirectories that contain either `Season-*` subdirectories or at least one episode-pattern filename directly.
- **FR-314:** Under a **tv** root, the application shall recursively discover supported video files inside a show directory (under `Season-*` directories and directly under the show directory). A video file shall be classified as an episode if **either** its filename matches an episode pattern (§5.5.2) **or** it resides inside a `Season-*` directory. A video file matching neither shall still be recorded as `kind='episode'` with `parse_status='unparsed'`, `show_key` taken from the show directory, and `season`/`episode` NULL.
- **FR-315:** Discovery shall ignore unsupported extensions.
- **FR-316:** A directory whose name ends in `.mkv` or `.mp4` shall not be returned as a media file.
- **FR-317:** By default, symlinks shall **not** be followed. This shall be configurable via `general.follow_symlinks`.
- **FR-318:** Hidden files and directories (`.`-prefixed) shall be skipped by default. Configurable via `general.include_hidden`.
- **FR-319:** Directories whose basename matches any pattern in `general.skip_dirs` shall be skipped (default list in §9.1).
- **FR-320:** Unreadable files or directories shall be reported to the log, counted in `filesystem_errors`, and skipped; discovery shall not abort because of a single unreadable entry.
- **FR-321:** At scan time, registered root paths shall be canonicalized (resolved). If one registered root is an ancestor of another, only the ancestor shall be scanned and the descendant skipped, with a WARNING log. A media file shall never be recorded twice in one scan.
- **FR-322:** If a registered root path does not exist (e.g. an external drive is unmounted), the application shall log a WARNING, increment `filesystem_errors`, mark the scan `partial`, and **skip missing-file marking for that root in this scan**. Files under an unmounted root shall not be marked missing.
- **FR-323:** If a file's `(size, mtime_ns)` changes between initial stat and commit (modified during scan), the application shall discard that file's probe/hash results for the current scan, log at DEBUG, and not commit them. The file is retried on the next scan.
- **FR-324:** During recursive traversal, the application shall track visited real paths (resolved) and skip re-visits, preventing infinite symlink cycles.

### 5.5 Parsing

#### 5.5.1 Movies

- **FR-400:** For each discovered movie file, the application shall attempt to extract a **title** and a **year** from the filename using, in order:
  1. `Title (Year) [junk].ext`
  2. `Title.Year.Resolution.Source.Codec.ext`
  3. `Title.Year.Resolution.ext`
  4. `Title.Year.ext`
- **FR-401:** A **junk-token denylist** shall be applied to strip known non-title tokens: `1080p`, `720p`, `2160p`, `480p`, `BluRay`, `BRRip`, `WEB-DL`, `WEBRip`, `HDTV`, `x264`, `x265`, `H.264`, `HEVC`, `AAC`, `DTS`, `DDP`, `10bit`, etc. The list lives in `mediavault/constants.py` and is extensible.
- **FR-402 (normalization):** Parsed movie titles shall be stored in **two derived forms**:
  - **Display title** (`parsed_title`): the title only (year stored separately in `parsed_year`; resolution/source/codec/extension excluded), words separated by a **single whitespace**, **title-cased** per token. Example: `A Clockwork Orange`.
  - **Match key** (used for equality/near-dup): the display title **lowercased** with whitespace replaced by **underscores**. Example: `a_clockwork_orange`.
  - **Separators:** whitespace, `.`, `_`, and `-` are word separators. **Punctuation** (apostrophes, etc.) is **dropped** and is not a separator: `Schindler's List` → display `Schindlers List`, key `schindlers_list`; `Spider-Man` → display `Spider Man`, key `spider_man`.
- **FR-403:** Parsed information shall be stored in `parsed_*` columns, distinct from any future canonical metadata.
- **FR-404:** The original filename and full path shall always be preserved, even if parsing fails entirely.

#### 5.5.2 Television

- **FR-410:** For each discovered episode file, the application shall attempt to extract `(show_key, season, episode)` from the **directory structure first**:
  - Show key from the show directory name: display form `Breaking Bad` (whitespace-separated, title-case); match key `breaking_bad` (lowercased, underscore-separated). Same separator/punctuation rules as FR-402.
  - Season from a `Season-<n>` directory name (FR-415).
- **FR-411:** If season is not present in a directory name (one-season shows), the season shall be taken from the filename.
- **FR-412:** Episode number shall be taken from the filename.
- **FR-413:** The canonical episode filename pattern is `Show.Title.S<SS>E<EE>.<rest>.<ext>`. Additionally accepted for tolerance: `Show.Title.1x02.<rest>.<ext>` and `Show.Title.Season.1.Episode.2.<rest>.<ext>`.
- **FR-414:** When the show title in the filename disagrees with the show directory name, the **directory name wins**.
- **FR-414a:** When the season number implied by a `Season-<n>` directory disagrees with the `S<SS>` in the filename (e.g. `Season-2/…S01E03…`), the **directory wins**. The filename's season is recorded as a parsing note in the log (debug level).
- **FR-415 (season directories):**
  - `Season-<n>` is accepted where `<n>` is a **positive integer**.
  - For seasons 1–9: accept unpadded (`Season-1`…`Season-9`) **and** single-zero-padded (`Season-01`…`Season-09`).
  - For seasons ≥10: accept **unpadded only** (`Season-10`, `Season-11`, …).
  - **Rejected:** `Season-0`, `Season-00`, `Season-001`, `Season-010` (zero or redundant padding). Non-matching directories are treated as ordinary directories.
- **FR-416:** If the filename yields no episode number but the file is inside a `Season-*` directory, the episode shall be recorded with `episode = NULL` and `parse_status = 'partial'`.
- **FR-417:** Parsed info is stored in `parsed_*` columns; the original path and filename are always preserved.
- **FR-418:** If the filename yields no episode number **and** the file is not inside a `Season-*` directory (but is inside a show directory), the file is recorded as `kind='episode'`, `parse_status='unparsed'`, `season`/`episode` NULL (FR-314).

#### 5.5.3 Shared parsing rules

- **FR-420:** Parsing shall tolerate filenames that do not match any pattern and shall not throw; unmatched files receive `parse_status = 'unparsed'`.
- **FR-421:** Each parsed record shall store `parse_status ∈ {ok, partial, unparsed}` and `parse_confidence ∈ {high, medium, low}` (heuristic).
- **FR-422:** Parsing shall be deterministic and side-effect-free; it shall not touch the filesystem.

### 5.6 Technical metadata (FFprobe)

- **FR-500:** The application shall invoke FFprobe (path from config; default `ffprobe` on `PATH`) for each media file whose probe cache is invalid. The probe cache identity is `(size, mtime_ns, ffprobe_version)`: if any component differs from the stored values, the file shall be re-probed.
- **FR-501:** The following fields shall be extracted when present:
  - `format_name`
  - `duration` (seconds)
  - `bit_rate`
  - video: `codec_name`, `width`, `height`
  - audio: `codec_name`, `channels`, `language` (first audio stream; additional streams' summaries stored as JSON in `audio_streams_json`)
  - subtitles: `has_embedded_subs BOOL`, `embedded_sub_count INT`, `embedded_sub_langs TEXT` (comma-separated)
- **FR-502:** `width` and `height` shall be read from the **video stream**, not from `format`. If no video stream exists, `width` and `height` shall be `NULL`.
- **FR-503:** If FFprobe fails for a file, the file's probe fields shall be `NULL`, an error shall be logged at WARNING, `probe_errors` shall be incremented, and the scan shall continue. Failure handling:
  - The subprocess shall be invoked with `timeout=general.ffprobe_timeout_seconds`. On timeout, the process is killed, a WARNING logged with path and `"timeout"`, and the file treated as failed.
  - Captured stderr shall be truncated to `general.ffprobe_stderr_max_chars` (default 2000) in log messages.
  - Malformed or empty JSON, or a non-zero exit code, shall be treated as a probe failure.
  - There is **no in-scan retry**; failed probes are retried on the next scan.
- **FR-504:** A file whose `(size, mtime_ns, ffprobe_version)` matches its most recent **successful** probed values shall not be re-probed. A failed probe is never cached as valid.
- **FR-505:** The FFprobe invocation shall use JSON output (`-print_format json -show_format -show_streams`).
- **FR-506:** The application shall not fabricate metadata on FFprobe failure. All probe fields shall be `NULL`.
- **FR-507:** When FFprobe is missing at scan start, the application shall warn once and proceed with an empty-metadata scan:
  - probe fields `NULL` for all files;
  - `has_embedded_subs = NULL` (unknown, not false) for all files;
  - `probe_errors` incremented;
  - the scan's `status` shall be `partial` (exit 3);
  - exact-duplicate hashing and external subtitle discovery (which are independent of FFprobe) shall still run.

### 5.7 Subtitle discovery and matching

- **FR-600:** The application shall record whether each media file has **embedded subtitles** (MKV only, via FR-501).
- **FR-601:** For each media file, the application shall search external subtitle files in the order defined in §4.3:
  1. `M.parent / f"{S}.srt"`
  2. `M.parent / "subs" / f"{S}.srt"`
  3. For every ancestor `A` of `M.parent` up to and including the scan root: `A / "subs" / f"{S}.srt"`
- **FR-602:** The `subtitles` table shall hold both external and embedded subtitle records:
  - `kind ∈ {external, embedded}` (CHECK constraint).
  - `path` is nullable; embedded rows have `path = NULL`.
  - For embedded subtitles, **one summary row per media file** shall be recorded (carrying count/languages as available), in addition to the denormalized `media_files` fields.
  - All external matches found shall be recorded; the first in §4.3 order shall be marked `is_primary = 1`.
  - An embedded row shall be marked `is_primary = 1` **only if** the file has no external subtitle.
- **FR-603:** Extension **and** stem matching shall be case-insensitive for `.srt`. The actual on-disk path shall be recorded (preserving case). If multiple case-variant `.srt` files match the same stem in the same location, all shall be recorded; the primary within that location shall be the lexicographically first, and a DEBUG note logged.
- **FR-604:** Unmatched external subtitle files (`.srt` files under any scan root that match no media file) shall be recorded as **orphan subtitles** and be listable in reports.
- **FR-605:** The presence of embedded subs **and** an external subtitle file shall both be reported; they are not mutually exclusive.
- **FR-606:** Additional subtitle formats (`.ass`, `.ssa`, `.sub`, `.vtt`) and language suffix parsing (`movie.en.srt`) are **out of scope for v1** and listed in §12.2.

### 5.8 Duplicate detection

#### 5.8.1 Exact duplicates

- **FR-700:** The application shall detect byte-identical media files by full **SHA-256** hash of file contents, irrespective of filename, extension, or directory. Extension is metadata only and never a grouping key.
- **FR-701:** Hashing shall be **staged**:
  1. Group candidate files by **`size` only**; sizes that appear once are skipped.
  2. For candidate groups, read the **first and last `partial_hash_bytes`** (default 64 KiB) of each file and compute a partial hash. Files whose partial hash is unique within the group are skipped. If `size ≤ 2 * partial_hash_bytes`, the whole file is read once (no overlapping double-read).
  3. For remaining candidates, compute the full SHA-256 using chunks of at most `hash_chunk_bytes`.
- **FR-702:** Staged hashing parameters shall be configurable: `duplicates.hash_chunk_bytes` (full-hash read chunk), `duplicates.partial_hash_bytes` (start/end partial read size).
- **FR-703:** Duplicate detection shall never delete, move, or modify files.
- **FR-704:** Each duplicate group shall be recorded with a `group_id`; each file in the group shall reference it.
- **FR-705:** Duplicate results shall be associated with the scan run that produced them (`scan_id`).
- **FR-706:** Hashes for unchanged files (`(size, mtime_ns)` match) shall be reused from the previous scan and not recomputed.

#### 5.8.2 Near-duplicates

- **FR-710:** The application shall compute and store a **similarity key** for each movie and each episode:
  - Movies: `(normalized_title_key, parsed_year)` (key lowercased per FR-402; `year` may be `NULL`). Files without a year are **excluded** from near-dup grouping.
  - Episodes: `(show_key, season, episode)`. Files missing any of these are **excluded** from near-dup grouping.
- **FR-711:** A near-duplicate group is created for a similarity key **only when at least two distinct content hashes exist** within that key. The group includes **all** files sharing the key (including exact-duplicate members), and each member's `hash_value` is retained so exact copies can be annotated.
- **FR-712:** Near-duplicate results shall be recorded per scan (`scan_id`) and reported as groups with their member paths and hash annotations.
- **FR-713:** Similarity keys shall be stored in a dedicated column (`near_dup_key TEXT`) so that a future perceptual-hash mechanism (v1.1) can co-exist without a schema change.
- **FR-714:** Near-duplicate detection shall be **read-only** with respect to the media files.

### 5.9 Database

- **FR-800:** The application shall use a local SQLite database (stdlib `sqlite3`) at the path from configuration (`general.db_path`; default `~/.local/share/mediavault-cli/mediavault.db`).
- **FR-801:** On connection, the application shall set `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`.
- **FR-802:** The schema shall be versioned using `PRAGMA user_version` and migrated by ordered SQL files in `mediavault/database/migrations/`, executed by `mediavault/database/migrator.py`.
- **FR-802a (migration rules):**
  - **Immutability (binding):** an already-applied migration file shall **never** be modified. Schema changes require a new migration.
  - Each migration shall run inside a transaction; on failure, that migration is rolled back and the database remains at the last successfully applied version. The application logs an ERROR and exits 1.
  - If `user_version` is **greater** than the latest version known to the code, the application shall refuse to run with a clear error ("database schema is newer than this version of MediaVault; upgrade the app") and exit 1.
- **FR-803:** The schema shall contain at least these tables (see `docs/schema.md` for DDL):
  - `scan_roots(id, path, root_type, added_at, last_scan_id)`
  - `scans(id, started_at, ended_at, status, movies_found, shows_found, episodes_found, exact_duplicates_found, near_duplicates_found, filesystem_errors, probe_errors, hash_errors, errors_count)`
  - `scan_roots_scanned(scan_id, scan_root_id)` — which roots participated in each scan
  - `media_files` (one row per discovered file; `path` is the identity in v1; includes `size`, `mtime_ns`, `last_seen_scan_id`, `missing_since_scan_id`, `near_dup_key`, parsed and probed columns)
  - `scan_media_files(scan_id, media_file_id, discovered_at, scan_status)` — historical membership (composite PK)
  - `movies(id, media_file_id, franchise)` — link/attribute table only; no duplicated parsed title
  - `shows(id, show_key UNIQUE, display_name)`
  - `seasons(id, show_id, number)`
  - `episodes(id, media_file_id, show_id, season_id, episode_number)`
  - `subtitles(id, media_file_id, path, kind, is_primary, missing_since_scan_id)`
  - `duplicate_groups(id, scan_id, kind)` — `kind ∈ {exact, near}`
  - `duplicate_members(group_id, media_file_id, hash_value)`
  - `meta(key, value)` — `schema_version`, `ffprobe_version`, `last_successful_scan_id`
- **FR-804:** All SQL access shall be mediated by `mediavault.database.repository`; no module outside `mediavault.database` shall import `sqlite3`.
- **FR-805:** File identity in v1 is the **path**. Renames and moves are treated as delete + add (FR-806).
- **FR-806:** When a file seen in a previous scan is not seen in the current scan (and its root was mounted/scanned), its row shall be marked `missing_since_scan_id = <current scan_id>`. It shall **not** be deleted. Missing-marking is skipped for roots that were unmounted (FR-322).
- **FR-807:** When a previously-missing file is seen again, its `missing_since_scan_id` shall be cleared.
- **FR-808:** The database shall retain `parsed_*` and `probed_*` information in separate columns (transparency per NFR-009).
- **FR-809:** The database shall record `ffprobe_version` and `schema_version` in a `meta` table for diagnostics.
- **FR-810 (constraints):** `docs/schema.md` shall define and the schema shall enforce:
  - **Foreign keys** on every relational column (with `PRAGMA foreign_keys=ON`).
  - **NOT NULL** on identity/required columns (e.g. `media_files.path`, `size`, `mtime_ns`, `kind`).
  - **CHECK** constraints: `media_files.kind IN ('movie','episode')`; `scans.status IN ('running','completed','partial','failed')`; `subtitles.kind IN ('external','embedded')`; `parse_status IN ('ok','partial','unparsed')`; `duplicate_groups.kind IN ('exact','near')`.
  - **UNIQUE** constraints: `media_files.path`, `shows.show_key`, `movies.media_file_id`, `episodes.media_file_id`, `(seasons.show_id, number)`, `(scan_media_files.scan_id, scan_media_files.media_file_id)`.
- **FR-811 (indexes):** The schema shall include indexes on: `media_files.last_seen_scan_id`, `media_files.missing_since_scan_id`, `media_files.kind`, `media_files.parsed_title`, `media_files.parsed_year`, `media_files.near_dup_key`; `episodes.show_id`, `episodes.season_id`; `duplicate_groups.scan_id`; `scan_media_files.scan_id`.

### 5.10 Browse and search

- **FR-900:** `browse movies` shall display movies in a `rich` table with columns: title, year, resolution, codec, subtitle (ext/embedded/none), path.
- **FR-901:** `browse shows` shall list shows with episode counts and total season count.
- **FR-902:** `browse episodes [--show NAME] [--season N]` shall list episodes for the given show and optional season.
- **FR-903:** `search` shall support filters: `--title`, `--year`, `--codec`, `--min-width`, `--show`, `--season`, `--episode`, `--resolution WxH`, `--min-duration S`, `--max-duration S`, and the subtitle filters below. Filters combine with AND.
  - `--has-subs` = external **OR** embedded.
  - `--has-external-subs` = external only.
  - `--has-embedded-subs` = embedded only.
  - `--no-subs` = neither.
- **FR-903a:** Conflicting filter combinations shall be rejected as usage errors (exit 2). At minimum: `--has-subs` with `--no-subs`; `--has-external-subs` with `--no-subs`; `--has-embedded-subs` with `--no-subs`.
- **FR-904:** By default, all browse and search results shall **exclude** missing files (`missing_since_scan_id IS NOT NULL`). A `--include-missing` flag shall include them.
- **FR-905:** Results shall be paginated when they exceed one terminal screen; navigation via arrow keys in the menu, or `--page N` in non-interactive mode.

### 5.11 Analysis (menu item 6)

- **FR-1000:** `analyze` shall produce a **read-only**, database-backed report of:
  - Codec distribution (counts per codec, movie vs. episode breakdown).
  - Resolution distribution (counts per `WIDTHxHEIGHT`, movie vs. episode).
  - Subtitle coverage: percentage of files with external subs, with embedded subs, with both, with neither (movie vs. episode).
- **FR-1001:** `analyze` shall not invoke FFprobe or touch the filesystem.
- **FR-1002:** `analyze` shall accept `--scan N` to restrict analysis to files that were members of the given scan (via `scan_media_files`), using their **currently stored** metadata. Default: latest successful scan. *(Historical analysis uses current metadata; per-scan metadata snapshots are deferred — §12.2.)*
- **FR-1003:** Output shall be `rich` tables in interactive mode and in non-interactive mode.

### 5.12 Reports and export

- **FR-1100:** `export` shall support `--format {txt,csv,md}` in v1. Google Sheets is deferred to v1.1.
- **FR-1101:** `export` shall support `--scope {full,movies,show}` and, when `--scope=show`, a required `--show NAME`.
- **FR-1102:** Movie report columns: `title`, `year`, `resolution`, `codec`, `duration_s`, `has_external_subs`, `has_embedded_subs`, `duplicate_group`, `path`.
- **FR-1103:** Episode report columns: `show`, `season`, `episode`, `resolution`, `codec`, `duration_s`, `has_external_subs`, `has_embedded_subs`, `duplicate_group`, `path`.
- **FR-1104:** A "problem report" section shall list: orphan subtitles, files missing external subtitles, unparsed files, files with probe errors, and missing files.
- **FR-1105:** Reports shall be written under `general.report_output_dir` (default `~/.local/share/mediavault-cli/reports`), with filenames `<scope>-<timestamp>.<ext>`.
- **FR-1106:** CSV output shall use UTF-8 with a header row and RFC 4180 quoting.
- **FR-1107:** Markdown output shall use tables with a header row per section.
- **FR-1108:** TXT output shall be plain, sectioned, human-readable.
- **FR-1109:** Report generation shall not modify the database.
- **FR-1110:** The application shall **reject** any resolved `report_output_dir` that lies inside a registered scan root, with a clear error and exit 1. (Protects the read-only scan-root guarantee, NFR-002.)

### 5.13 Configuration and environment

- **FR-1200:** Configuration shall be read from, in precedence order (highest first):
  1. CLI flags
  2. Environment variables (prefix `MEDIAVAULT_CLI_`)
  3. Project-local config
  4. `~/.config/mediavault-cli/config.toml` (XDG)
  5. Built-in defaults

  **Project-local selection:** if `MEDIAVAULT_CLI_CONFIG` is set, that file **replaces** the project-local source and `./config.toml` is **not** read; the XDG file remains the fallback. If unset, the project-local source is `./config.toml`.
- **FR-1201:** The configuration file format shall be **TOML**, except for `pytest`, which uses `pytest.ini`.
- **FR-1202:** The configuration schema shall match §9.1.
- **FR-1203:** `mediavault-cli config show` shall print the **resolved** configuration, its source per key, and the database path in use.
- **FR-1204:** `mediavault-cli config init` shall write a default `config.toml` to `./config.toml` if none exists; it shall refuse to overwrite an existing file unless `--force`.
- **FR-1205:** `mediavault-cli config paths` shall print the resolved XDG and project-local config paths, DB path, log dir, and report output dir.
- **FR-1206:** Environment variables shall include `MEDIAVAULT_CLI_DB_PATH`, `MEDIAVAULT_CLI_LOG_DIR`, `MEDIAVAULT_CLI_LOG_LEVEL`, `MEDIAVAULT_CLI_FFPROBE_PATH`, `MEDIAVAULT_CLI_CONFIG`. Other config keys may be overridable by env in v1.1.
- **FR-1207:** Secrets (e.g. Google credentials, in v1.1) shall be accepted **only** from environment variables or a credentials file referenced from env. They shall never be read from the committed TOML.
- **FR-1208:** A configuration file that exists but is invalid (malformed TOML or schema violation) shall produce a clear error and exit code **1**; settings shall never be silently ignored. Missing files are treated as absent.

### 5.14 Logging

- **FR-1300:** The application shall configure the dedicated **`"mediavault"`** logger (not the root logger) in `logging_setup.configure_logging(level, log_dir, log_filename)`. Initialization shall be idempotent (repeated calls shall not add duplicate handlers).
- **FR-1301:** Logging shall emit to both a console handler (level = configured `log_level`; INFO by default) and a `RotatingFileHandler` (DEBUG, max 5 MB × 3 backups) at `<log_dir>/mediavault-cli.log`.
- **FR-1302:** During an interactive menu session, the console handler shall use level WARNING to keep the UI readable; the file handler still records DEBUG.
- **FR-1303:** The following events shall be logged at INFO or above:
  - scan start (roots, scan_id)
  - scan end (counters, duration, status)
  - each FFprobe failure (WARNING, with path and truncated stderr)
  - each unreadable file or directory (WARNING)
  - each root skipped due to overlap or being unmounted (WARNING)
  - each database migration applied (INFO)
  - each scan aborted due to lock contention (ERROR)
  - each invalid configuration (ERROR)
- **FR-1304:** The following shall be logged at DEBUG:
  - each parsed result and its `parse_status`
  - each subtitle match decision (which location matched)
  - each hashing stage entry/exit for a file
  - `auto` root classification decisions (FR-105a)
  - unstable-file detections (FR-323)
- **FR-1305:** Credentials, tokens, and any value from a secret-source env var shall never be logged.
- **FR-1306:** Log records emitted during a scan shall include the `scan_id` in a structured field (via `LoggerAdapter` or contextvar).
- **FR-1307:** Per-category error counters (`filesystem_errors`, `probe_errors`, `hash_errors`) shall be recorded on each scan alongside the aggregate `errors_count` (FR-102).

### 5.15 Menu footer and status line

- **FR-1400:** The interactive menu shall display, before the options list, a status line populated from the latest successful scan (`completed` or `partial`):
  - `Last scan: #<scan_id> at <timestamp> (<status>)`
  - `Movies: <n>  Shows: <n>  Episodes: <n>  Exact dups: <n>  Near dups: <n>`
- **FR-1401:** If no successful scan exists, the footer shall read `No scans yet — choose 1 to scan.`

---

## 6. Non-Functional Requirements

- **NFR-001 — Data safety:** Scanning, analysis, and reporting shall not modify, rename, move, or delete original media files.
- **NFR-002 — Read-only scan roots:** The application shall never write inside a scan root. Database, logs, reports, and configuration live under XDG or project-local paths. Export output paths inside a scan root are rejected (FR-1110).
- **NFR-003 — Robustness:** Empty directories, nested directories, unsupported files, inconsistent filenames, unreadable files, broken symlinks, symlink cycles, unmounted roots, and missing FFprobe shall be handled without crashing the whole scan.
- **NFR-004 — Error handling:** Per-file errors shall be logged, categorized, and counted; the scan continues. Fatal errors (invalid root, unwritable DB, missing migrations directory, future schema version, invalid config) shall exit non-zero per FR-207 with a clear message.
- **NFR-005 — Maintainability:** Modules shall follow the layout in §7; responsibilities are separated; no module outside `mediavault.database` imports `sqlite3`; core modules do not import `typer`, `rich`, or `questionary`.
- **NFR-006 — Testability:** Core logic shall be unit-testable without a real media collection. Tests shall use `tmp_path` and mock `subprocess.run` for FFprobe. A small set of integration tests marked `@pytest.mark.integration` may require real `ffprobe`.
- **NFR-007 — Portability:** All path handling shall use `pathlib`. No hard-coded absolute paths.
- **NFR-008 — Single writer:** Concurrent scans shall be prevented by an **exclusive OS advisory lock** (`fcntl.flock`) on `<db_dir>/.scan.lock`. The lock file may persist on disk; the OS releases the lock when the owning process exits, including on crash. No PID-based staleness checks are used. A second scan invocation shall exit non-zero (1) with a clear message.
- **NFR-009 — Transparency:** Parsed and probed information shall be stored in distinct columns and reported distinctly.
- **NFR-010 — Performance:** Staged hashing (FR-701) and probe reuse for unchanged files (FR-504) shall be applied. A scan shall process files sequentially in v1; parallelism is deferred.
- **NFR-011 — Security:** Secrets shall come only from env or env-referenced files. Logs shall never include secret values.
- **NFR-012 — Observability:** A rotating log file, per-scan counters (including per-category error counts), and `scan_id` in log records together shall allow post-hoc diagnosis of any scan.
- **NFR-013 — Python version compatibility:** Every third-party dependency shall be verified against Python 3.14 before v1 sign-off (DEP-01).
- **NFR-014 — Reproducibility:** `pytest` shall be runnable via a single command (`pytest`) with no manual setup beyond installing the package in editable mode.
- **NFR-015 — Import boundaries:** An automated check shall verify that (a) no module outside `mediavault.database` imports `sqlite3`, and (b) core modules (`discovery`, `parsing`, `metadata`, `subtitles`, `duplicates`) do not import `typer`, `rich`, or `questionary`. Service modules mediate between CLI and core.

---

## 7. Software Architecture

```
mediavault-cli/
├── mediavault/
│   ├── __init__.py
│   ├── __main__.py              # delegates to mediavault.cli.main:app
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py              # Typer app (entry point target)
│   │   ├── menu.py              # interactive menu (questionary/InquirerPy); calls services only
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
│   ├── services/                # application/orchestration layer
│   │   ├── __init__.py
│   │   ├── scanner.py           # coordinates the scan workflow
│   │   ├── library.py           # browse/search/query orchestration
│   │   ├── analyzer.py          # read-only analysis
│   │   └── duplicate_service.py # duplicate detection + persistence
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
│   │   ├── migrator.py          # runs migrations/ (NOT migrations.py)
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
│   └── utils.py                 # generic, dependency-free helpers only (see rule below)
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
│   ├── test_import_boundaries.py
│   └── database/
│       ├── test_connection.py
│       ├── test_schema.py
│       ├── test_migrator.py
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

**Architectural rules (binding):**
- **CLI → Services → Core / Repository.** `cli/*` (including `menu.py`) calls `services/*`; it contains no business logic.
- **Core isolation:** `discovery`, `parsing`, `metadata`, `subtitles`, `duplicates` do not import `typer`, `rich`, or `questionary`.
- **DB isolation:** only `mediavault.database` imports `sqlite3`.
- **`utils.py`:** restricted to genuinely generic, dependency-free helpers (e.g. byte humanization, safe truncation). Domain helpers live in `paths.py`, `parsing.py`, or the relevant report module.
- **Migration naming:** the runner is `migrator.py`; `migrations/` holds immutable, ordered SQL files only.
- **Packaging:** `[project.scripts] mediavault-cli = "mediavault.cli.main:app"`. `__main__.py` delegates to the same app. Any pre-parse setup (logging, config) runs inside the Typer app callback.
- **Rule:** Empty placeholder modules are not created. A module exists because it implements functionality covered by a requirement.

---

## 8. Data Model (summary; DDL in `docs/schema.md`)

**Entities** (fields abbreviated):

- **`scan_roots(id, path, root_type, added_at, last_scan_id)`** — `root_type ∈ {movies, tv, auto}` (CHECK).
- **`scans(id, started_at, ended_at, status, movies_found, shows_found, episodes_found, exact_duplicates_found, near_duplicates_found, filesystem_errors, probe_errors, hash_errors, errors_count)`** — `status ∈ {running, completed, partial, failed}` (CHECK); `errors_count = filesystem_errors + probe_errors + hash_errors`.
- **`scan_roots_scanned(scan_id, scan_root_id)`** — composite PK; records which roots participated in each scan.
- **`media_files(id, path UNIQUE, filename, extension, kind, size, mtime_ns, last_seen_scan_id, missing_since_scan_id, parsed_title, parsed_year, parse_status, show_key, season, episode, near_dup_key, codec, width, height, duration, bit_rate, audio_codec, audio_channels, audio_streams_json, has_embedded_subs, embedded_sub_count, embedded_sub_langs, probed_at, ffprobe_version)`** — `kind ∈ {movie, episode}` (CHECK).
- **`scan_media_files(scan_id, media_file_id, discovered_at, scan_status)`** — composite PK `(scan_id, media_file_id)`; authoritative historical membership.
- **`movies(id, media_file_id UNIQUE, franchise)`** — link/attribute table only; no duplicated parsed title (canonical titles deferred, §12.2).
- **`shows(id, show_key UNIQUE, display_name)`** — `display_name` title-cased, whitespace-separated; `show_key` lowercased, underscore-separated.
- **`seasons(id, show_id, number)`** — UNIQUE `(show_id, number)`.
- **`episodes(id, media_file_id UNIQUE, show_id, season_id, episode_number)`**.
- **`subtitles(id, media_file_id, path, kind, is_primary, missing_since_scan_id)`** — `kind ∈ {external, embedded}` (CHECK); `path` nullable for embedded; embedded `is_primary=1` only when no external exists.
- **`duplicate_groups(id, scan_id, kind)`** — `kind ∈ {exact, near}` (CHECK).
- **`duplicate_members(group_id, media_file_id, hash_value)`**.
- **`meta(key, value)`** — `schema_version`, `ffprobe_version`, `last_successful_scan_id`.

File identity in v1 is `media_files.path` (FR-805). FKs, NOT NULL, CHECK, UNIQUE, and indexes are mandated by FR-810/FR-811.

---

## 9. Configuration and Environment Variables

### 9.1 TOML schema (see `docs/config.example.toml`)

```toml
[general]
db_path                   = "~/.local/share/mediavault-cli/mediavault.db"
log_dir                   = "~/.local/state/mediavault-cli/logs"
log_level                 = "INFO"                 # DEBUG | INFO | WARNING | ERROR
ffprobe_path              = "ffprobe"
ffprobe_timeout_seconds   = 60
ffprobe_stderr_max_chars  = 2000
subs_dir_name             = "subs"
report_output_dir         = "~/.local/share/mediavault-cli/reports"
probe_skip_unchanged      = true
follow_symlinks           = false
include_hidden            = false
skip_dirs                 = ["@eaDir", "#recycle", ".Trash-*", "$RECYCLE.BIN", "System Volume Information"]

[scan]
default_roots = []                                 # list of { path, root_type }

[duplicates]
hash_chunk_bytes   = 1048576                       # max chunk for full SHA-256 reads
partial_hash_bytes = 65536                         # bytes read from start AND end

# v1.1:
# [google]
# credentials_file = ""
# sheet_id         = ""
```

### 9.2 Environment variables

| Variable | Maps to | Notes |
|---|---|---|
| `MEDIAVAULT_CLI_CONFIG` | Project-local config path | **Replaces** `./config.toml`; XDG still fallback |
| `MEDIAVAULT_CLI_DB_PATH` | `general.db_path` | |
| `MEDIAVAULT_CLI_LOG_DIR` | `general.log_dir` | |
| `MEDIAVAULT_CLI_LOG_LEVEL` | `general.log_level` | |
| `MEDIAVAULT_CLI_FFPROBE_PATH` | `general.ffprobe_path` | |

Precedence (FR-1200): CLI flags > env > project-local config > XDG `config.toml` > defaults. Invalid config → exit 1 (FR-1208).

---

## 10. Testing and Acceptance Criteria

Tests are written with `pytest`. `conftest.py` provides:

- `tmp_library` — creates a temporary directory tree matching §4.
- `memory_db` — an in-memory SQLite database with migrations applied.
- `fake_ffprobe` — a fixture that monkeypatches `subprocess.run` to return canned FFprobe JSON.
- `sample_paths` — filename corpus from §4.1, §4.2, §4.4, including edge cases.

### 10.1 Component acceptance criteria (abbreviated)

- **Discovery (FR-310–324):** nested `.mkv`/`.mp4` found; uppercase extensions found; unsupported ignored; dir named `x.mkv` not returned; empty dir → empty result; symlinks/hidden/junk-dirs respected; unreadable subdir does not abort; `Season-*` under a movies root skipped; `auto` classifies each file once.
- **Parsing (FR-400–422):** four movie patterns parse; junk denylist strips tokens; `Breaking.Bad.S05E12.1080p.mp4` → `show_key=breaking_bad`, `season=5`, `episode=12`; `Season-01/…S01E02` → season 1; **`Season-2/…S01E03…` → season 2 (directory wins)**; `Season-0`/`Season-00`/`Season-001`/`Season-010` rejected; normalization: `A.Clockwork.Orange.1971.1080p.mkv` → display `A Clockwork Orange`, key `a_clockwork_orange`; `Schindler's.List` → `Schindlers List` / `schindlers_list`.
- **Metadata (FR-500–507):** parse canned FFprobe JSON; missing video stream → width/height NULL; embedded subs counted; unchanged `(size, mtime_ns, ffprobe_version)` not re-probed; version change → re-probe; FFprobe failure → all probe fields NULL, `probe_errors++`; timeout kills process; missing FFprobe → `partial`, embedded NULL, hashing+ext-subs still run.
- **Subtitles (FR-600–606):** all five layouts from §4.3 matched; case-insensitive stem+ext matching; multiple case-variants recorded; orphan `.srt` recorded; embedded summary row recorded; embedded-only media recorded as having subs; embedded `is_primary` only when no external.
- **Duplicates (FR-700–714):** staged hashing groups identical files; byte-identical `.mkv`/`.mp4` of the same size compared and reported; single-size files skipped; small files (`size ≤ 2*partial_hash_bytes`) read once; near-dup key groups different-resolution copies; near-dup group requires ≥2 distinct hashes; exact copies annotated.
- **Database (FR-800–811):** migrations apply from empty; re-scan marks missing files; unmounted root does **not** mark files missing; returning files clear `missing_since_scan_id`; `PRAGMA user_version` matches `schema_version`; FK enforcement; CHECK constraints reject invalid values; expected indexes present.
- **Search / browse (FR-900–905):** filters AND-combine; `--has-subs` = external OR embedded; conflicting filters → exit 2; missing files excluded by default, included with `--include-missing`.
- **Reports (FR-1100–1110):** TXT/CSV/MD produced with required columns; orphan-subtitles section present; output dir inside a scan root rejected.
- **CLI / menu (FR-200–209):** each subcommand supports `--help`; exit codes 0/1/2/3 observed; `scan` flag rules (repeatable `--root`, `--root`/`--last` exclusive, no-flag default); menu launches and exits; menu item 1 handles zero roots; "re-scan last roots" with no prior scan is graceful.
- **Config (FR-1200–1208):** precedence order observed; `MEDIAVAULT_CLI_CONFIG` replaces project-local; invalid config → exit 1; `config show` prints sources; `config init --force` overwrites, otherwise refuses.

### 10.2 Named integration scenarios

**Integration — initial scan:**
- Input: 3 movies, 1 show, 2 seasons, 4 episodes, 2 external subtitles (under a `movies` root and a `tv` root).
- Expected: 3 movies, 1 show, 4 episodes discovered; 2 subtitles matched; DB populated; `scan_media_files` has 7 rows for the scan; `status=completed`; exit 0.

**Integration — second scan:**
- Initial: Movies A, B, C. Second: A, C, D.
- Expected: B marked `missing_since_scan_id`; D inserted; A, C updated; historical membership preserved (`scan_media_files` has 3 rows for scan 1 and 3 for scan 2); last-successful updates.

**Integration — modified file:**
- Initial: Movie A (1080p). Replace with a 2160p file (same path, new size/mtime).
- Expected: FFprobe runs again; metadata updated; old metadata not reused.

### 10.3 Discovery edge-case table

| Test | Expected behavior |
|---|---|
| Empty scan root | Empty result |
| Missing scan root at scan time | WARNING, `filesystem_errors++`, `partial`, files not marked missing |
| Unreadable directory | Log and continue |
| Broken symlink | Skip |
| Symlink cycle | No infinite traversal (FR-324) |
| Directory ending in `.mkv` | Ignore as a directory |
| Hidden directory | Skip by default |
| Nested `subs/` directory | Never classify SRT files as video |
| Two roots, one an ancestor of the other | Only ancestor scanned; WARNING; no duplicate records |

### 10.4 Configuration precedence scenarios

**Named example:** default `INFO` → XDG `WARNING` → project `DEBUG` → env `ERROR` → CLI `CRITICAL` ⇒ resolved `CRITICAL`.

Also tested: each source missing; invalid TOML → exit 1; schema-violating value → exit 1; `MEDIAVAULT_CLI_CONFIG` replacing `./config.toml`.

### 10.5 Migration tests

From empty; already-current; multiple pending; failed migration rollback; future `user_version` refusal; FK enforcement; expected indexes present.

---

## 11. Development Milestones

Adopted from the v1.1 review. The goal is a working end-to-end application as early as possible; the interactive menu is built last, on top of working non-interactive commands.

| Phase | Component | Deliverable |
|---|---|---|
| 1 | Project setup | Packaging (`[project.scripts]`), dependencies, pytest, logging; verify all deps on Python 3.14 (DEP-01) |
| 2 | Models and constants | `errors.py`, `constants.py`, `models.py` |
| 3 | Path validation | `paths.py` + tests |
| 4 | Discovery | `discovery.py` (root-type driven) + tests |
| 5 | Parsing | `parsing.py` (movie + episode + normalization) + tests |
| 6 | Database foundation | `connection.py`, `migrator.py`, `0001_init.sql`, `repository.py` + tests |
| 7 | Scan orchestration | `services/scanner.py`; end-to-end scan (discovery→parse→persist) + tests |
| 8 | FFprobe | `metadata.py` (cache, timeout, failure) + tests |
| 9 | Subtitles | `subtitles.py` + tests |
| 10 | Exact duplicates | staged SHA-256 in `duplicates.py` + tests |
| 11 | Near duplicates | similarity-key grouping + tests |
| 12 | Browse and search | `services/library.py`, queries + tests |
| 13 | Analysis | `services/analyzer.py` + tests |
| 14 | Reports | `reports/` (txt, csv, md) + tests |
| 15 | CLI and menu | Typer app, subcommands, then `menu.py` (calls services only) + tests |
| 16 | Integration testing | §10.2–§10.5 scenarios |
| 17 | Documentation | `README.md`, `docs/schema.md`, `docs/logging.md` |

---

## 12. Open Questions and Deferred Decisions

### 12.1 Resolved from SRS v0.1 (for the record)

All ten open questions from v0.1 have been resolved during specification and are now requirements in §5.

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
10. **Per-scan metadata snapshots** — for full historical fidelity of `analyze --scan N`. v1 records membership only (`scan_media_files`) and uses current metadata.

### 12.3 Residual ambiguities

All residual ambiguities (OPEN-Q-1, OPEN-Q-2, OPEN-Q-3) have been resolved and promoted to requirements in v1.2 (see §13.1). No open items remain from the v1.1 review.

---

## 13. Change Management

This specification is version 1.2. Changes follow:

- Update the affected requirement(s) in place.
- Keep requirement identifiers stable; deprecated requirements are marked `[DEPRECATED]` rather than renumbered.
- Add tests for any newly defined behavior.
- New open questions are added to §12.3 with an ID (`[OPEN-Q-n]`) and closed only by promoting to a requirement.
- Version bumps: **minor** for requirements added/changed, **patch** for wording, **major** for scope removal or an incompatible schema decision (with the caveat that pre-implementation schema refinement is treated as minor).

### 13.1 v1.1 review — resolutions applied in v1.2

| Review item | Resolution | Requirement(s) |
|---|---|---|
| §1.1 Scan-root classification | `root_type ∈ {movies, tv, auto}` | FR-100, FR-105, FR-105a |
| §1.2 Historical scan membership | `scan_media_files` join table; snapshots deferred | FR-102a, FR-803, FR-1002, §12.2#10 |
| §1.3 Exact-dup extension grouping | Group by `size` only | FR-700, FR-701 |
| §1.4 Partial-hashing config | `hash_chunk_bytes` + `partial_hash_bytes`; small-file rule | FR-701, FR-702, §9.1 |
| §1.5 Migration naming conflict | `migrator.py` + `migrations/` | FR-802, §7 |
| §1.6 Report dir inside scan root | XDG default; reject inside scan root | FR-1105, FR-1110, NFR-002 |
| §2.1 Near-dup semantics | ≥2 distinct hashes; include all; annotate | FR-710–FR-712 |
| §2.2 Subtitle representation / case | `kind ∈ {external, embedded}`; nullable path; case-insensitive stem+ext | FR-602, FR-603, FR-600 |
| §2.3 Season dir wording | Explicit accept/reject table | FR-415 |
| §2.4 Discovery overlap / extras | Movies skip `Season-*`; TV = pattern-or-season-dir | FR-312, FR-314, FR-418 |
| §2.5 FFprobe cache / failures | `(size, mtime_ns, ffprobe_version)`; retry failures; timeout | FR-500, FR-503, FR-504, FR-507 |
| §2.6 Config file selection | `MEDIAVAULT_CLI_CONFIG` replaces project-local; invalid → exit 1 | FR-1200, FR-1208 |
| §2.7 Lock semantics | `fcntl.flock`; no PID checks | NFR-008 |
| §2.8 Scan status vocabulary | `running/completed/partial/failed`; successful = completed\|partial | FR-102, FR-103, FR-207 |
| §3.2 DB constraints/indexes | Mandated in SRS; DDL in `docs/schema.md` | FR-810, FR-811 |
| §3.3 `movies`/`episodes` duplication | Link-table only; canonical deferred | FR-803, §8 |
| §4.1 Service layer | `services/` (scanner, library, analyzer, duplicate_service) | §7, NFR-015 |
| §4.2 `utils.py` policy | Binding placement rule | §7 |
| §4.3 Migration immutability | Binding rule; per-migration tx; future-version refusal | FR-802a |
| §4.4 Packaging entry point | `[project.scripts]` + `__main__` delegation | §7 |
| §5.1 FR-208 JSON inconsistency | JSON out of scope in v1 | FR-208 |
| §5.2 Export scope inconsistency | Appendix A aligned to `--scope` | FR-1101, Appendix A |
| §5.3 Scan flag behavior | Repeatable `--root`; exclusive `--last`; no-flag default | FR-203a |
| §5.4 Search filters | Explicit subs semantics; new filters; conflicts → exit 2 | FR-903, FR-903a |
| §6.1 Logger namespace | `"mediavault"` logger; idempotent init | FR-1300 |
| §6.2 Error counters | Per-category counters | FR-102, FR-1307 |
| §6.3 Subprocess failure details | Timeout, truncation, malformed handling | FR-503 |
| §7 Test additions | Integration, discovery edge, config precedence | §10.2–§10.5 |
| §7.2 Overlapping/unmounted/modified/cycles | Explicit rules | FR-321–FR-324 |
| §8.1–8.2 Milestone order | 17-phase order; menu last | §11 |
| §12.3 Residual ambiguities | Normalization/matching rules finalized | FR-402, FR-410, FR-604 |
| Version | v1.2, minor, with revision history | Header, §13 |

---

## Appendix A — Resolved decisions from the specification dialogue (traceability)

| Decision | Answer | Where it lives |
|---|---|---|
| CLI modes | Menu + non-interactive subcommands + `--help` | FR-200–FR-209 |
| CLI framework | Typer (subcommands/flags), questionary/InquirerPy (menu), Rich (tables) | §3.2, §7 |
| Drive detection | Linux volume detection + manual path entry | FR-101 |
| Multiple scan roots | Yes | FR-100, FR-805 |
| Scan root type | `movies`, `tv`, `auto` | FR-100, FR-105, FR-105a |
| `auto` behavior | Both passes + per-file precedence | FR-105a |
| Exit codes | Conventional 0/1/2/3 | FR-207 |
| Scan runs as first-class | Yes, `scan_id` | FR-102 |
| Scan statuses | `running/completed/partial/failed`; successful = completed\|partial | FR-102, FR-103 |
| Historical scan membership | `scan_media_files` join table; snapshots deferred | FR-102a, §12.2#10 |
| File identity | Path (renames = delete+add) | FR-805 |
| Stale files | Marked missing, not deleted; skipped for unmounted roots | FR-806, FR-322 |
| Hashing strategy | Staged: size → partial (`partial_hash_bytes`) → full SHA-256 (`hash_chunk_bytes`) | FR-701, FR-702 |
| Exact-dup grouping | By `size` only; extension is metadata | FR-700, FR-701 |
| DB layer | stdlib `sqlite3`, repository-mediated | FR-800, FR-804 |
| DB constraints/indexes | FKs, NOT NULL, CHECK, UNIQUE, indexes mandated | FR-810, FR-811 |
| Migration rules | Immutability; per-migration tx; future-version refusal | FR-802a |
| Google Sheets | Deferred to v1.1 | FR-1100, §12.2 |
| Python floor | 3.14 | §3.1, NFR-013 |
| Console command | `mediavault-cli` | front matter, FR-200 |
| Packaging entry point | `mediavault-cli = "mediavault.cli.main:app"`; `__main__` delegates | §7 |
| Dependency policy | Typer + Rich + questionary/InquirerPy + stdlib + pytest (+ Google libs in v1.1) | §3.2 |
| Config format | TOML (pytest uses INI) | FR-1201 |
| Config precedence | CLI > env > project-local > XDG > defaults | FR-1200 |
| `MEDIAVAULT_CLI_CONFIG` | Replaces `./config.toml`; XDG fallback; invalid → exit 1 | FR-1200, FR-1208 |
| Subtitle layouts | Ancestor `subs/` rule + embedded | FR-601, §4.3 |
| Subtitle representation | `kind ∈ {external, embedded}`; nullable path; embedded primary only if no external | FR-602 |
| Subtitle case matching | Case-insensitive stem + extension; record all; lexicographic primary | FR-603 |
| Movie patterns | Four patterns + junk denylist | FR-400–FR-401 |
| Movie normalization | Display: title-only, whitespace-separated, title-case; key: lowercased, underscore-separated; punctuation dropped | FR-402 |
| Episode pattern | `Show.Title.SxxEyy…` + tolerated variants | FR-413 |
| Show normalization | Display: whitespace-separated, title-case; key: lowercased, underscore-separated | FR-410 |
| Season zero-padding | 1–9 permissive (`Season-1`/`Season-01`); 10+ unpadded; zero/triple-zero rejected | FR-415 |
| Show title authority | Directory wins, filename is fallback | FR-414 |
| **Season conflict** | **Directory wins** | **FR-414a** |
| Discovery overlap | Movies skip `Season-*`; TV = pattern-or-season-dir, else unparsed episode | FR-312, FR-314, FR-418 |
| Overlapping/unmounted roots | Canonicalize; ancestor wins; unmounted → partial, no missing-marking | FR-321, FR-322 |
| Files modified during scan | Discard results; retry next scan | FR-323 |
| Symlink cycles | Visited-path guard | FR-324 |
| FFprobe fields | Format + video + audio + embedded subs + dims | FR-501–FR-502 |
| Probe cache | `(size, mtime_ns, ffprobe_version)`; failures retried; timeout | FR-500, FR-503, FR-504 |
| Missing FFprobe | `partial`; embedded NULL; hashing+ext-subs run | FR-507 |
| Duplicate scope | Exact (byte-identical) **and** near (similarity key) | FR-700–FR-714 |
| Near-dup key | Metadata-derived (title+year / show+season+episode) | FR-710 |
| Near-dup grouping | ≥2 distinct hashes; include all; annotate | FR-711, FR-712 |
| Report scope | `--scope {full,movies,show}` + `--show` | FR-1101 |
| Report output dir | XDG default; reject inside scan root | FR-1105, FR-1110 |
| Symlinks / hidden / junk | Not followed / skipped / denylist | FR-317–FR-319 |
| Search filters | Explicit subs semantics + show/season/episode/resolution/duration; conflicts → exit 2 | FR-903, FR-903a |
| Logging | `"mediavault"` logger; idempotent; per-category counters | FR-1300, FR-1307 |
| Single writer | `fcntl.flock` lock file | NFR-008 |
| Scan roots read-only | Never write inside | NFR-002, FR-1110 |
| Architecture | CLI → services → core/repository; import boundaries enforced | §7, NFR-015 |
| `utils.py` | Generic helpers only | §7 |
| Milestones | 17-phase; menu last | §11 |
| Version | v1.2 (minor) | Header, §13 |

---

**End of SRS v1.2.**