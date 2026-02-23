"""Unit tests for app.core.logging."""

import pytest

from app.core.logging import configure_logging


@pytest.mark.parametrize("log_level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_configure_logging_runs_without_error(log_level):
    configure_logging(log_level)
