"""Vina's output, parsed once for both backends.

The Python API and the command-line binary print the same progress lines and
write the same PDBQT, so neither backend owns this parsing: `worker.py` consumes
it while a run is live, and the CLI backend can reuse it without importing the
worker (which would drag a child-process module into the server process).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Final

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


#: The energy table ``vina --score_only`` / ``--local_only`` prints. Values are
#: checked against the Python API's own breakdown in
#: ``tests/unit/test_score_table_parser.py`` — names are not trusted on their own.
_TABLE_PATTERNS: Final = {
    "total": re.compile(r"Estimated Free Energy of Binding\s*:\s*(-?\d+(?:\.\d+)?)"),
    "inter": re.compile(r"\(1\) Final Intermolecular Energy\s*:\s*(-?\d+(?:\.\d+)?)"),
    "intra": re.compile(r"\(2\) Final Total Internal Energy\s*:\s*(-?\d+(?:\.\d+)?)"),
    "torsions": re.compile(r"\(3\) Torsional Free Energy\s*:\s*(-?\d+(?:\.\d+)?)"),
    "intra_best": re.compile(r"\(4\) Unbound System's Energy\s*:\s*(-?\d+(?:\.\d+)?)"),
}


def parse_score_table(stdout: str) -> dict[str, float]:
    """The five energies our ``ScoreResponse`` reports, read off Vina's table.

    The CLI prints the same decomposition the Python API returns as an eight-value
    array (``[total, lig_inter, flex_inter, other_inter, flex_intra, lig_intra,
    torsions, lig_intra best pose]``): ``(1)`` is the sum of the three
    intermolecular terms, ``(2)`` the sum of the two internal ones, and ``(4)``
    matches the last column. Every field must be present — a partially parsed
    table would report zeros as if they were energies.
    """
    values: dict[str, float] = {}
    for name, pattern in _TABLE_PATTERNS.items():
        match = pattern.search(stdout)
        if match is None:
            raise ValueError(
                f"Vina's output has no {name!r} line — this does not look like a "
                "score table; refusing to report zeros as energies"
            )
        values[name] = float(match.group(1))
    return values
