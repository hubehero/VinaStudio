"""Logging configuration shared by the desktop shell, server and workers."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from vinastudio.config import logs_dir

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO, *, to_file: bool = True) -> None:
    """Configure root logging once, writing to stderr and a rotating file."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(level)

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(stream)

    if to_file:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                logs_dir() / "vinastudio.log",
                maxBytes=4 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        except OSError:  # pragma: no cover - unwritable home directory
            file_handler = None
        if file_handler is not None:
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            root.addHandler(file_handler)

    # uvicorn installs its own handlers; keep its output consistent with ours.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    _configured = True
