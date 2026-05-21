"""
core/logging_config.py
----------------------
PURPOSE:
    Centralised logging setup for the entire backend.
    Every module calls get_logger(__name__) to get a named, consistently
    formatted logger. Logs go to BOTH the console and a rotating file in
    the project's temp/ folder.

CONCEPTS:
    - Python logging hierarchy: root logger → child loggers (named by module).
    - StreamHandler  → writes to console (stdout).
    - FileHandler    → writes to a .log file on disk.
    - RotatingFileHandler → auto-rolls log files when they exceed MAX_BYTES,
      keeping the last BACKUP_COUNT old files. Prevents disk fill-up.
    - Formatter      → controls the log line format.
    - Level hierarchy: DEBUG < INFO < WARNING < ERROR < CRITICAL.

LOG OUTPUT:
    Console  → coloured, human-readable (INFO+ level)
    File     → temp/app.log  (INFO+ level, rotates at 5 MB, keeps 3 backups)
    Test runs output to temp/<script_name>.log automatically when
    setup_file_logging(name) is called from the test script.

USAGE:
    from core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.warning("Something unexpected")
    logger.error("Something broke", exc_info=True)   # exc_info attaches traceback
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Resolved relative to the backend/ working directory (where uvicorn is started).
# Go up one level to reach the project root, then into temp/.
TEMP_DIR = Path(__file__).resolve().parent.parent.parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)

_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


def _configure_root_logger() -> None:
    """
    Attach a console StreamHandler and a rotating FileHandler to the root logger.

    Called once at module import time. Safe to import multiple times —
    we guard against adding duplicate handlers.

    Console handler:
        - Writes to stdout (readable in terminal and in IDE output panels).
        - Encodes non-ASCII characters with 'replace' so Windows cp1252
          consoles don't raise UnicodeEncodeError on special characters.

    File handler (RotatingFileHandler):
        - Writes to temp/app.log.
        - Rotates when the file exceeds 5 MB; keeps 3 backup files
          (app.log.1, app.log.2, app.log.3).
        - Always UTF-8 so log files are readable on any OS.
    """
    root = logging.getLogger()

    # Guard: don't add handlers a second time if this module is re-imported.
    if root.handlers:
        return

    root.setLevel(logging.INFO)

    # ── Console handler ──────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_formatter)

    # Wrap the stream to replace unencodable characters (e.g. Unicode arrows
    # that Windows cp1252 can't display) instead of raising an exception.
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(errors="replace")
        except Exception:
            pass  # not all stream types support reconfigure

    root.addHandler(console_handler)

    # ── Rotating file handler ────────────────────────────────────────────────
    log_file = TEMP_DIR / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(_formatter)
    root.addHandler(file_handler)

    # ── Suppress noisy third-party loggers ───────────────────────────────────
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger for a module.

    Args:
        name: Pass __name__ so log lines show the module path,
              e.g. 'auth.router' or 'agents.query_engine'.

    Returns:
        A standard logging.Logger instance ready to use.
    """
    return logging.getLogger(name)


def setup_file_logging(script_name: str) -> Path:
    """
    Add a dedicated log file for a test/script run in temp/.

    Call this at the top of test scripts to get a separate, named log file:
        setup_file_logging("test_query_engine")
        → writes to temp/test_query_engine.log

    The dedicated file captures only that script's run, making it easy to
    review the last test result without digging through app.log.

    Args:
        script_name: Base name for the log file (no extension).

    Returns:
        Path to the created log file.
    """
    log_file = TEMP_DIR / f"{script_name}.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
        mode="w",   # overwrite on each test run (keeps last run only)
    )
    handler.setFormatter(_formatter)
    logging.getLogger().addHandler(handler)
    return log_file
