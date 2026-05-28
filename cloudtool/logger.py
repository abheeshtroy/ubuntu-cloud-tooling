"""
logger.py
Configures structured logging for ubuntu-cloud-tooling.
Writes to both stdout and a log file simultaneously.
Every module imports get_logger() from here.
"""

import logging
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Default log file location — overridden by CLI --log-file flag
DEFAULT_LOG_FILE = Path("cloudtool.log")


def setup_logging(log_file: Path = DEFAULT_LOG_FILE, verbose: bool = False) -> None:
    """
    Call once at startup from cli.py.
    Sets up the root logger with a stdout handler and a file handler.

    Args:
        log_file: Path to write the log file.
        verbose:  If True, set level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers if called more than once (e.g. in tests)
    if root.handlers:
        root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- stdout handler ---
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)
    root.addHandler(stdout_handler)

    # --- file handler ---
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)  # always verbose in file
        root.addHandler(file_handler)
    except OSError as exc:
        # Non-fatal: log to stdout only if file is not writable
        logging.warning("Could not open log file %s: %s", log_file, exc)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Call this at the top of every module:
        log = get_logger(__name__)
    """
    return logging.getLogger(name)