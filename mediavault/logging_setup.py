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


class _MediaVaultConsoleHandler(logging.StreamHandler):
    """Handler subclass used as an identity marker (no custom attrs)."""


class _MediaVaultFileHandler(RotatingFileHandler):
    """Handler subclass used as an identity marker (no custom attrs)."""


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


def configure_logging(
    level: str = "INFO",
    log_dir: str | Path | None = None,
    log_filename: str = "mediavault-cli.log",
    console_level: str | None = None,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Idempotency: if our handlers are already installed, we're done.
    if any(isinstance(h, (_MediaVaultConsoleHandler, _MediaVaultFileHandler))
           for h in logger.handlers):
        return logger

    formatter = logging.Formatter(_LOG_FORMAT)

    console = _MediaVaultConsoleHandler()
    console.setLevel(getattr(logging, (console_level or level).upper()))
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_dir is not None:
        log_path = Path(log_dir).expanduser()
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = _MediaVaultFileHandler(
            log_path / log_filename,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
