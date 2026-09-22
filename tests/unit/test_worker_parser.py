"""Unit tests for the Vina stdout parser in the worker module."""

from __future__ import annotations

from vinastudio.core.worker import (
    _DOCKING_RE,
    _GRID_RE,
    _PROGRESS_RE,
    _RESULTS_RE,
)


def test_grid_re() -> None:
    assert _GRID_RE.search("Computing Vina grid ...")
    assert _GRID_RE.search("  Computing Vina grid ...")
    assert not _GRID_RE.search("Performing docking")


def test_docking_re() -> None:
    assert _DOCKING_RE.search("Performing docking (random seed: 42) ...")
    assert not _DOCKING_RE.search("Computing Vina grid")


def test_results_re() -> None:
    assert _RESULTS_RE.search("mode | affinity | rmsd l.b. | rmsd u.b.")
    assert _RESULTS_RE.search("mode  |  affinity  |  rmsd l.b.  |  rmsd u.b.")
    assert not _RESULTS_RE.search("0% .. 10%")


def test_progress_re_single() -> None:
    match = _PROGRESS_RE.search("0%")
    assert match is not None
    assert match.group(1) == "0"

    match = _PROGRESS_RE.search("100%")
    assert match is not None
    assert match.group(1) == "100"

    assert _PROGRESS_RE.search("50%") is not None
    assert _PROGRESS_RE.search("no number here") is None


def test_progress_re_in_vina_line() -> None:
    """The regex uses search(), so it finds the first percentage on the line."""
    line = "0% .. 10% .. 20% .. 30% .. 40% .. 50% .. 60% .. 70% .. 80% .. 90% .. 100%"
    match = _PROGRESS_RE.search(line)
    assert match is not None
    assert match.group(1) == "0"


def test_full_vina_output_pattern() -> None:
    """Simulate parsing a realistic Vina stdout sequence."""
    lines = [
        "Computing Vina grid ...",
        "done.",
        "Performing docking (random seed: 20260920) ...",
        "0% .. 10% .. 20% .. 30% .. 40% .. 50% .. 60% .. 70% .. 80% .. 90% .. 100%",
        "-----+------------+----------+----------",
        "   1        -8.342      0.000      0.000",
        "   2        -8.105      1.234      2.567",
        "mode | affinity | rmsd l.b. | rmsd u.b.",
    ]

    stages_found = []
    progress_found = False

    for line in lines:
        if _GRID_RE.search(line):
            stages_found.append("computing_grid")
        elif _DOCKING_RE.search(line):
            stages_found.append("docking")
        elif _RESULTS_RE.search(line):
            stages_found.append("exporting")
        elif _PROGRESS_RE.search(line):
            progress_found = True

    assert stages_found == ["computing_grid", "docking", "exporting"]
    assert progress_found
