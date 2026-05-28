"""
Tests for logger.py
"""

import logging
from pathlib import Path
from cloudtool.logger import setup_logging, get_logger


def test_logger_writes_to_file(tmp_path):
    log_file = tmp_path / "test.log"
    setup_logging(log_file=log_file, verbose=False)

    log = get_logger("test.module")
    log.info("hello from test")

    assert log_file.exists()
    contents = log_file.read_text()
    assert "hello from test" in contents


def test_verbose_mode_enables_debug(tmp_path):
    log_file = tmp_path / "test.log"
    setup_logging(log_file=log_file, verbose=True)

    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_setup_logging_idempotent(tmp_path):
    """Calling setup_logging twice should not duplicate handlers."""
    log_file = tmp_path / "test.log"
    setup_logging(log_file=log_file)
    setup_logging(log_file=log_file)

    root = logging.getLogger()
    assert len(root.handlers) == 2  # exactly stdout + file, not 4