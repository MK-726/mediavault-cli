"""configure_logging is idempotent (FR-1300)."""

import logging

from mediavault.logging_setup import LOGGER_NAME, configure_logging


def test_configure_logging_is_idempotent(tmp_path):
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger._mediavault_configured = False  # reset between tests

    configure_logging(level="INFO", log_dir=tmp_path)
    configure_logging(level="INFO", log_dir=tmp_path)

    console_handlers = [
        h for h in logger.handlers if not hasattr(h, "baseFilename")]
    file_handlers = [h for h in logger.handlers if hasattr(h, "baseFilename")]

    assert len(console_handlers) == 1
    assert len(file_handlers) == 1
