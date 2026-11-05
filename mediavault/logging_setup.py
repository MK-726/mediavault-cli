"""Logging configuration (FR-1300, FR-1301, NFR-012).

The application uses the dedicated "mediavault" logger, never the root
logger. configure_logging() is idempotent: repeated calls do not add
duplicate handlers.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "mediavault"
_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the application logger (or a child of it)."""
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


def configure_logging(
    level: str = "INFO",
    log_dir: str | Path | None = None,
    log_filename: str = "mediavault-cli.log",
    console_level: str | None = None,
) -> logging.Logger:
    """Configure the "mediavault" logger idempotently.

    Parameters
    ----------
    level:
        File-handler level (DEBUG by default in practice; FR-1301).
    log_dir:
        Directory for the rotating file. If None, file logging is skipped
        (useful for tests and early bootstrapping).
    log_filename:
        Rotating log file name.
    console_level:
        Console-handler level. Defaults to *level*. During an interactive
        menu session, pass "WARNING" to keep the UI readable (FR-1302).
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)  # handlers do the filtering
    logger.propagate = False        # don't leak to the root logger

    # Idempotency guard: if we've already installed our handlers, stop.
    if getattr(logger, "_mediavault_configured", False):
        return logger

    formatter = logging.Formatter(_LOG_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, (console_level or level).upper()))
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_dir is not None:
        log_path = Path(log_dir).expanduser()
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / log_filename,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger._mediavault_configured = True  # type: ignore[attr-defined]
    return logger
