""""""

import logging

import pytest

from mediavault.logging_setup import LOGGER_NAME


@pytest.fixture(autouse=True)
def _reset_mediavault_logger():
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        h.close()
    logger.handlers.clear()
