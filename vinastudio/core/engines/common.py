"""Vina's output, parsed once for both backends.

The Python API and the command-line binary print the same progress lines and
write the same PDBQT, so neither backend owns this parsing: `worker.py` consumes
it while a run is live, and the CLI backend can reuse it without importing the
worker (which would drag a child-process module into the server process).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

#: Lines Vina prints when ``verbosity >= 1`` (v1.2.7).
_GRID_RE = re.compile(r"Computing Vina grid")
_DOCKING_RE = re.compile(r"Performing docking")
_PROGRESS_RE = re.compile(r"(\d+)%")
_RESULTS_RE = re.compile(r"mode\s*\|\s*affinity")


def events_for_line(line: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """The events one stdout line implies, in the order they should be sent.

    A recognised banner is reported as a stage change *instead of* a log line —
    the stage is the news, and echoing the banner would only duplicate it.
    Anything else is a log line, plus a ``progress`` event when the line carries
    a percentage.
    """
    if _GRID_RE.search(line):
        yield "stage", {"stage": "computing_grid"}
    elif _DOCKING_RE.search(line):
        yield "stage", {"stage": "docking"}
    elif _RESULTS_RE.search(line):
        yield "stage", {"stage": "exporting"}
    else:
        match = _PROGRESS_RE.search(line)
        if match:
            yield "progress", {"percent": int(match.group(1))}
        yield "log", {"line": line}
