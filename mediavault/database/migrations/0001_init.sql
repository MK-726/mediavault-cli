-- 0001_init.sql
-- Initial MediaVault schema (FR-803, FR-810, FR-811)

-- 1. Scan roots (FR-100, FR-105)
CREATE TABLE scan_roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    root_type TEXT NOT NULL CHECK (root_type IN ('movies', 'tv', 'auto')),
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL
);

-- 2. Scans (FR-102)
CREATE TABLE scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ended_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'partial', 'failed')
    ),

    movies_found INTEGER NOT NULL DEFAULT 0,
    shows_found INTEGER NOT NULL DEFAULT 0,
    episodes_found INTEGER NOT NULL DEFAULT 0,
    exact_duplicates_found INTEGER NOT NULL DEFAULT 0,
    near_duplicates_found INTEGER NOT NULL DEFAULT 0,

    filesystem_errors INTEGER NOT NULL DEFAULT 0,
    probe_errors INTEGER NOT NULL DEFAULT 0,
    hash_errors INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0
);

-- 3. Scan Roots Scanned (FR-102, joining scans to roots)
CREATE TABLE scan_roots_scanned (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    scan_root_id INTEGER NOT NULL REFERENCES scan_roots(id) ON DELETE CASCADE,
    PRIMARY KEY (scan_id, scan_root_id)
);

-- 4. Media Files (FR-803, §8)
CREATE TABLE media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('movie', 'episode')),
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,

    last_seen_scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
    missing_since_scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,

    -- Parsed metadata (FR-403, FR-808)
    parsed_title TEXT,
    parsed_year INTEGER,
    parse_status TEXT NOT NULL DEFAULT 'unparsed' CHECK (
        parse_status IN ('ok', 'partial', 'unparsed')
    ),
    parse_confidence TEXT NOT NULL DEFAULT 'low' CHECK (
        parse_confidence IN ('high', 'medium', 'low')
    ),

    show_key TEXT,
    season INTEGER,
    episode INTEGER,

    near_dup_key TEXT,

    -- Probed metadata (FR-501)
    codec TEXT,
    width INTEGER,
    height INTEGER,
    duration REAL,
    bit_rate INTEGER,
    audio_codec TEXT,
    audio_channels INTEGER,
    audio_streams_json TEXT,
    has_embedded_subs BOOLEAN,
    embedded_sub_count INTEGER,
    embedded_sub_langs TEXT,
    probed_at TEXT,
    ffprobe_version TEXT
);

-- 5. Scan Media Files (FR-102a, historical membership)
CREATE TABLE scan_media_files (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    discovered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    scan_status TEXT NOT NULL DEFAULT 'seen' CHECK (scan_status IN ('seen', 'missing')),
    PRIMARY KEY (scan_id, media_file_id)
);

-- 6. Movies (FR-803, link-table only)
CREATE TABLE movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_file_id INTEGER NOT NULL UNIQUE REFERENCES media_files(id) ON DELETE CASCADE,
    franchise TEXT
);

-- 7. Shows (FR-803)
CREATE TABLE shows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);

-- 8. Seasons (FR-803)
CREATE TABLE seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    UNIQUE (show_id, number)
);

-- 9. Episodes (FR-803)
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_file_id INTEGER NOT NULL UNIQUE REFERENCES media_files(id) ON DELETE CASCADE,
    show_id INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
    season_id INTEGER REFERENCES seasons(id) ON DELETE SET NULL,
    episode_number INTEGER
);

-- 10. Subtitles (FR-602)
CREATE TABLE subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_file_id INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    path TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('external', 'embedded')),
    is_primary BOOLEAN NOT NULL DEFAULT 0,
    missing_since_scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL
);

-- 11. Duplicate Groups (FR-704, FR-711)
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('exact', 'near'))
);

-- 12. Duplicate Members
CREATE TABLE duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    hash_value TEXT,
    PRIMARY KEY (group_id, media_file_id)
);

-- 13. Meta (FR-809)
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Seed meta values
INSERT INTO meta (key, value) VALUES ('schema_version', '1');
INSERT INTO meta (key, value) VALUES ('ffprobe_version', 'unknown');

-- Indexes (FR-811)
CREATE INDEX ix_media_files_last_seen ON media_files(last_seen_scan_id);
CREATE INDEX ix_media_files_missing_since ON media_files(missing_since_scan_id);
CREATE INDEX ix_media_files_kind ON media_files(kind);
CREATE INDEX ix_media_files_parsed_title ON media_files(parsed_title);
CREATE INDEX ix_media_files_parsed_year ON media_files(parsed_year);
CREATE INDEX ix_media_files_near_dup_key ON media_files(near_dup_key);
CREATE INDEX ix_episodes_show ON episodes(show_id);
CREATE INDEX ix_episodes_season ON episodes(season_id);
CREATE INDEX ix_duplicate_groups_scan ON duplicate_groups(scan_id);
CREATE INDEX ix_scan_media_files_scan ON scan_media_files(scan_id);
