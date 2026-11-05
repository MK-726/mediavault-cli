""""""


from mediavault.discovery import (
    discover_movie_files,
    discover_shows,
    discover_episode_files
)


def test_discover_movie_files(tmp_path):
    """Discover all MKV and MP4 files recursively."""

    movies_dir = tmp_path / "Movies"
    mcu_dir = movies_dir / "MCU"
    other_dir = movies_dir / "Other"

    mcu_dir.mkdir(parents=True)
    other_dir.mkdir()

    expected_files = [
        movies_dir / "Interstellar.2014.mp4",
        movies_dir / "The.Batman.2022.mkv",
        mcu_dir / "Iron.Man.2008.mkv",
        mcu_dir / "Avengers.Endgame.2019.mp4",
    ]

    for file in expected_files:
        file.touch()

    (movies_dir / "README.txt").touch()
    (other_dir / "Some.Movie.2020.avi").touch()

    result = discover_movie_files(movies_dir)
    assert set(result) == set(expected_files)


def test_discover_movie_files_empty_directory(tmp_path):
    """Return an empty list when the directory contains no files."""
    assert discover_movie_files(tmp_path) == []


def test_discover_movie_files_unsupported_extensions(tmp_path):
    """Ignore files with unsupported extensions."""
    (tmp_path / "movie.avi").touch()
    (tmp_path / "movie.mov").touch()
    (tmp_path / "notes.txt").touch()
    (tmp_path / "subtitles.srt").touch()

    assert discover_movie_files(tmp_path) == []


def test_discover_movie_files_uppercase_extensions(tmp_path):
    """Recognize uppercase video extensions."""
    mkv = tmp_path / "movie.MKV"
    mp4 = tmp_path / "movie.MP4"

    mkv.touch()
    mp4.touch()

    assert set(discover_movie_files(tmp_path)) == {mkv, mp4}


def test_discover_movie_files_ignores_directories(tmp_path):
    """Ignore directories even if they have video extensions."""
    directory = tmp_path / "movie.mkv"
    directory.mkdir()

    assert discover_movie_files(tmp_path) == []


def test_discover_movie_files_deeply_nested(tmp_path):
    """Discover video files in deeply nested directories."""
    nested_dir = tmp_path / "MCU" / "Phase-1" / "Iron-Man"
    nested_dir.mkdir(parents=True)

    movie = nested_dir / "Iron.Man.2008.mkv"
    movie.touch()

    assert discover_movie_files(tmp_path) == [movie]


def test_discover_movie_files_does_not_follow_symlinks(tmp_path):
    """"""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "movie.mkv").touch()
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(real_dir, target_is_directory=True)
    assert discover_movie_files(root) == []


def test_discover_movie_files_ignores_hidden(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / ".hidden.mkv").touch()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "other.mkv").touch()
    assert discover_movie_files(tmp_path) == [tmp_path / "movie.mkv"]


def test_discover_movie_files_skips_junk_dirs(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / "@eaDir" / "junk.mkv").touch()
    assert discover_movie_files(tmp_path) == [tmp_path / "movie.mkv"]


def test_discover_movie_files_unreadable_subdir_does_not_abort(tmp_path):
    (tmp_path / "good.mkv").touch()
    bad = tmp_path / "bad"
    bad.mkdir()
    bad.chmod(0o000)
    try:
        assert discover_movie_files(tmp_path) == [tmp_path / "good.mkv"]
    finally:
        bad.chmod(0o755)  # so pytest can clean up


def test_discover_shows(tmp_path):
    """Discover shows from immediate subdirectories."""

    shows_dir = tmp_path / "Shows"
    shows_dir.mkdir()

    expected_shows = [
        shows_dir / "Breaking-Bad",
        shows_dir / "Chernobyl",
        shows_dir / "Money-Heist",
    ]

    for show in expected_shows:
        show.mkdir()

    result = discover_shows(shows_dir)

    assert set(result) == set(expected_shows)


def test_discover_shows_empty_directory(tmp_path):
    """Return an empty list when no shows exist."""

    shows_dir = tmp_path / "Shows"
    shows_dir.mkdir()

    assert discover_shows(shows_dir) == []


def test_discover_shows_ignores_files(tmp_path):
    """Ignore files directly inside the shows directory."""

    shows_dir = tmp_path / "Shows"
    shows_dir.mkdir()

    (shows_dir / "notes.txt").touch()
    (shows_dir / "movie.mkv").touch()

    assert discover_shows(shows_dir) == []


def test_discover_shows_ignores_nested_directories(tmp_path):
    """Don't identify season directories as shows."""

    shows_dir = tmp_path / "Shows"
    season_dir = shows_dir / "Breaking Bad" / "Season-01"
    season_dir.mkdir(parents=True)

    result = discover_shows(shows_dir)

    assert result == [shows_dir / "Breaking Bad"]


def test_discover_episode_files_miniseries(tmp_path):
    """Discover episodes directly inside a show directory."""

    shows_dir = tmp_path / "Shows"
    mini_series_dir = shows_dir / "Chernobyl"
    mini_series_dir.mkdir(parents=True)

    expected_episodes = [
        mini_series_dir / f"Chernobyl.S01E{i:02}.1080p.mkv"
        for i in range(1, 6)
    ]

    for episode in expected_episodes:
        episode.touch()

    result = discover_episode_files(mini_series_dir)

    assert set(result) == set(expected_episodes)


def test_discover_episode_files_empty_directory(tmp_path):
    """Return an empty list when a show directory is empty."""

    show_dir = tmp_path / "Chernobyl"
    show_dir.mkdir()

    assert discover_episode_files(show_dir) == []


def test_discover_episode_files_empty_seasons(tmp_path):
    """Return an empty list when season directories contain no episodes."""

    show_dir = tmp_path / "Chernobyl"
    (show_dir / "Season-01").mkdir(parents=True)
    (show_dir / "Season-02").mkdir()

    assert discover_episode_files(show_dir) == []


def test_discover_episode_files_multiple_seasons(tmp_path):
    """Discover episodes across multiple season directories."""

    show_dir = tmp_path / "Breaking Bad"

    expected_episodes = [
        show_dir / f"Season-{season:02}" /
        f"Breaking.Bad.S{season:02}E{episode:02}.mkv"
        for season in range(1, 3)
        for episode in range(1, 3)
    ]

    for episode in expected_episodes:
        episode.parent.mkdir(parents=True, exist_ok=True)
        episode.touch()

    result = discover_episode_files(show_dir)

    assert set(result) == set(expected_episodes)


def test_discover_episode_files_unsupported_extensions(tmp_path):
    """Ignore files with unsupported extensions."""

    show_dir = tmp_path / "Chernobyl"
    show_dir.mkdir()

    unsupported_files = [
        "episode.avi",
        "episode.mov",
        "episode.txt",
        "episode.srt",
    ]

    for filename in unsupported_files:
        (show_dir / filename).touch()

    assert discover_episode_files(show_dir) == []


def test_discover_episode_files_uppercase_extensions(tmp_path):
    """Recognize uppercase video extensions."""

    show_dir = tmp_path / "Chernobyl"
    show_dir.mkdir()

    expected_episodes = [
        show_dir / "episode.MKV",
        show_dir / "episode.MP4",
    ]

    for episode in expected_episodes:
        episode.touch()

    result = discover_episode_files(show_dir)

    assert set(result) == set(expected_episodes)


def test_discover_episode_files_ignores_directories(tmp_path):
    """Ignore directories even if they have video extensions."""

    show_dir = tmp_path / "Chernobyl"
    show_dir.mkdir()

    (show_dir / "episode.mkv").mkdir()
    (show_dir / "episode.mp4").mkdir()

    assert discover_episode_files(show_dir) == []


def test_discover_episode_files_deeply_nested(tmp_path):
    """Discover video files in deeply nested directories."""

    show_dir = tmp_path / "Breaking Bad"

    nested_dir = (
        show_dir / "Season-01" / "Extras" / "Behind-the-Scenes"
    )
    nested_dir.mkdir(parents=True)

    episode = nested_dir / "episode.mkv"
    episode.touch()

    assert discover_episode_files(show_dir) == [episode]
