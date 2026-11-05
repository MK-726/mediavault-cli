"""configure_logging is idempotent (FR-1300)."""

import logging

from mediavault.logging_setup import (
    LOGGER_NAME,
    _MediaVaultConsoleHandler,
    _MediaVaultFileHandler,
    configure_logging,
)


def test_configure_logging_is_idempotent(tmp_path):
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()

    configure_logging(level="INFO", log_dir=tmp_path)
    configure_logging(level="INFO", log_dir=tmp_path)

    console = [h for h in logger.handlers if isinstance(
        h, _MediaVaultConsoleHandler)]
    files = [h for h in logger.handlers if isinstance(
        h, _MediaVaultFileHandler)]

    assert len(console) == 1
    assert len(files) == 1
