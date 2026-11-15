"""Keep engine output off the CLI's JSON stdout channel."""

from __future__ import annotations

import ctypes
import os
import sys
from contextlib import contextmanager, suppress


@contextmanager
def engine_output_to_stderr():
    """Redirect file descriptor 1 to stderr for C-level engine output.

    Vina's Python extension writes its progress table to fd 1, not through
    ``sys.stdout``. Redirecting the descriptor keeps ``--json`` parseable while
    the progress text remains available on stderr. C stdio is flushed before
    the descriptor is restored, otherwise a buffered table would appear after
    the JSON envelope.
    """
    saved = os.dup(1)
    try:
        if sys.stdout is not None:
            sys.stdout.flush()
        os.dup2(2, 1)
        yield
    finally:
        if sys.stdout is not None:
            sys.stdout.flush()
        with suppress(OSError, AttributeError):
            ctypes.CDLL(None).fflush(None)
        os.dup2(saved, 1)
        os.close(saved)
