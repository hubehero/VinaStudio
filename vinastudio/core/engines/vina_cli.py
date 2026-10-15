"""Docking through the official Vina command-line binary.

Same engine, different door. The Python module (`from vina import Vina`) has no
Windows build and neither does conda-forge, but upstream ships
``vina_1.2.7_win.exe`` — so on such a platform the binary is the only way in.

With a fixed seed the CLI and the Python API reproduce each other **exactly**
(verified on 1iep, exhaustiveness 8, seed 42: identical per-pose energies), so
this backend is held to the same golden expectations rather than a looser set.
It is not the default: the API path stays as it is, and nothing here runs until
a caller selects it (``engine="vina-cli"``).

Anything the CLI cannot express raises instead of being dropped — a silently
ignored option is a wrong result that looks right.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from vinastudio.config import PACKAGE_DIR
from vinastudio.core.docking import DockingParams, DockingResult, result_from_poses
from vinastudio.core.engines.common import parse_score_table

log = logging.getLogger(__name__)

#: Where ``scripts/fetch_vina_cli.py`` puts the binary.
CLI_DIR = PACKAGE_DIR / "resources" / "vina"
#: Point this at a binary of your own (any platform's build) to override.
CLI_PATH_ENV = "VINASTUDIO_VINA_CLI"

#: ``--num_modes`` default is 9, so it is always passed explicitly.
DEFAULT_NUM_MODES = 9


def cli_path() -> Path:
    """The Vina binary to run: an explicit override first, else the fetched one."""
    override = os.environ.get(CLI_PATH_ENV)
    if override:
        return Path(override).expanduser()
    for name in ("vina", "vina.exe"):
        candidate = CLI_DIR / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"no Vina CLI binary under {CLI_DIR} — run "
        "`uv run python scripts/fetch_vina_cli.py`, or point "
        f"{CLI_PATH_ENV} at one"
    )


def build_command(
    params: DockingParams,
    out_pdbqt: Path,
    ligand_path: str,
    binary: Path | None = None,
) -> list[str]:
    """The CLI invocation that reproduces ``params``.

    ``ligand_path`` is resolved by the caller, because an inline ligand string has
    to be written to a file first. Flag names are the ones the binary's own
    ``--help`` lists for v1.2.7, not guesses. Options with no CLI equivalent raise.
    """
    if params.no_refine:
        raise ValueError("the Vina CLI has no way to disable refinement (no_refine)")
    if params.weights is not None:
        raise ValueError("custom scoring weights are not exposed by the Vina CLI")

    command = [
        str(binary or cli_path()),
        "--receptor", params.receptor_path,
        "--ligand", ligand_path,
        "--center_x", str(params.center[0]),
        "--center_y", str(params.center[1]),
        "--center_z", str(params.center[2]),
        "--size_x", str(params.size[0]),
        "--size_y", str(params.size[1]),
        "--size_z", str(params.size[2]),
        "--scoring", params.scoring,
        "--exhaustiveness", str(params.exhaustiveness),
        "--num_modes", str(params.n_poses),
        "--energy_range", str(params.energy_range),
        "--min_rmsd", str(params.min_rmsd),
        "--max_evals", str(params.max_evals),
        "--spacing", str(params.spacing),
        "--cpu", str(params.cpu),
        "--seed", str(params.seed),
        "--verbosity", str(params.verbosity),
        "--out", str(out_pdbqt),
    ]
    if params.force_even_voxels:
        command.append("--force_even_voxels")
    if params.flex_pdbqt_path:
        command += ["--flex", params.flex_pdbqt_path]
    if params.map_prefix or params.map_paths:
        # ad4 (and any pre-computed vina maps) take the prefix the files are
        # named after; a box is ignored in that case, exactly as in the API.
        command += ["--maps", params.map_prefix or params.map_paths[0]]
    return command


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run Vina, turning a poor start or a non-zero exit into a readable error."""
    try:
        completed = subprocess.run(
            command,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE if capture else None,
            text=True,
            check=False,
        )
    except PermissionError as exc:
        raise RuntimeError(f"{command[0]} is not executable: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"{command[0]} not found: {exc}") from exc
    if completed.returncode != 0:
        lines = (completed.stderr or "").strip().splitlines()
        raise RuntimeError(
            f"vina exited with {completed.returncode}"
            + (f": {lines[-1]}" if lines else "")
        )
    return completed


def _ligand_file(params: DockingParams, target: Path) -> str:
    """The ligand as a path, writing an inline string out if that is all we have.

    The CLI takes files; keeping that detail here means the caller's contract
    (a path *or* a string) does not become a special case upstream.
    """
    if params.ligand_path:
        return params.ligand_path
    inline = target / "ligand.pdbqt"
    inline.write_text(params.ligand_pdbqt_string or "", encoding="utf-8")
    return str(inline)


def _box_flags(params: DockingParams) -> list[str]:
    return [
        "--center_x", str(params.center[0]),
        "--center_y", str(params.center[1]),
        "--center_z", str(params.center[2]),
        "--size_x", str(params.size[0]),
        "--size_y", str(params.size[1]),
        "--size_z", str(params.size[2]),
    ]


def _receptor_flags(params: DockingParams) -> list[str]:
    flags = ["--receptor", params.receptor_path]
    if params.flex_pdbqt_path:
        flags += ["--flex", params.flex_pdbqt_path]
    return flags


def run_docking_cli(params: DockingParams, output_dir: str) -> DockingResult:
    """Dock with the CLI binary and return the same result the API path returns.

    Stdout is *not* captured: the worker redirects its own stdout pipe for Vina's
    progress lines, and a child inherits that descriptor, so the existing reader
    keeps working unchanged for this backend. stderr is captured so a failure
    can be reported with the engine's own words.
    """
    binary = cli_path()
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)  # Vina refuses to write into a missing dir
    out_pdbqt = target / "poses.pdbqt"
    ligand_path = _ligand_file(params, target)

    command = build_command(params, out_pdbqt, ligand_path, binary)

    log.info("starting CLI docking: scoring=%s exhaustiveness=%d",
             params.scoring, params.exhaustiveness)

    start = time.monotonic()
    _run(command)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return result_from_poses(out_pdbqt, elapsed_ms)


def score_cli(params: DockingParams, work_dir: str) -> dict[str, float]:
    """Single-point score, as the five energies ``ScoreResponse`` reports.

    ``--verbosity 1`` is required, not cosmetic: the table is the output, and at
    verbosity 0 there is nothing to read.
    """
    target = Path(work_dir)
    target.mkdir(parents=True, exist_ok=True)
    command = [
        str(cli_path()),
        *_receptor_flags(params),
        "--ligand", _ligand_file(params, target),
        *_box_flags(params),
        "--scoring", params.scoring,
        "--spacing", str(params.spacing),
        "--verbosity", "1",
        "--score_only",
    ]
    if params.force_even_voxels:
        command.append("--force_even_voxels")
    if params.map_prefix or params.map_paths:
        command += ["--maps", params.map_prefix or params.map_paths[0]]

    stdout = _run(command, capture=True).stdout or ""
    return parse_score_table(stdout)


def optimize_cli(params: DockingParams, max_steps: int, work_dir: str) -> tuple[float, str]:
    """Local optimisation: the total energy plus the optimised conformation.

    Unlike the Python API — whose ``get_poses`` store stays empty after an
    ``optimize()`` call, so nothing can be exported — the binary writes the
    conformation with ``--out``. That is why this backend is used for the
    interactive pose operations even where the module is installed.
    """
    return _pose_and_energy(params, max_steps, work_dir, "--local_only")


def randomize_cli(params: DockingParams, max_steps: int, work_dir: str) -> str:
    """A random conformation, from ``--randomize_only --out``.

    ``--seed`` does **not** make this reproducible (the binary seeds itself; two
    runs with the same value differ), which is why no response claims otherwise.
    """
    _, pose = _pose_and_energy(params, max_steps, work_dir, "--randomize_only", want_energy=False)
    return pose


def _pose_and_energy(
    params: DockingParams,
    max_steps: int,
    work_dir: str,
    mode: str,
    *,
    want_energy: bool = True,
) -> tuple[float, str]:
    """Run one of the two pose-producing modes and read back what it wrote."""
    target = Path(work_dir)
    target.mkdir(parents=True, exist_ok=True)
    out_pdbqt = target / "pose.pdbqt"
    command = [
        str(cli_path()),
        *_receptor_flags(params),
        "--ligand", _ligand_file(params, target),
        *_box_flags(params),
        "--scoring", params.scoring,
        "--spacing", str(params.spacing),
        "--verbosity", "1",
        "--max_evals", str(max_steps),
        mode,
        "--out", str(out_pdbqt),
    ]
    if params.force_even_voxels:
        command.append("--force_even_voxels")
    if params.map_prefix or params.map_paths:
        command += ["--maps", params.map_prefix or params.map_paths[0]]

    stdout = _run(command, capture=True).stdout or ""
    if not out_pdbqt.is_file():
        # Silence here would be the worst outcome: a response claiming to carry a
        # conformation that was never written.
        raise RuntimeError(f"Vina reported success but wrote no conformation to {out_pdbqt}")
    pose = out_pdbqt.read_text(encoding="utf-8", errors="replace")
    energy = parse_score_table(stdout)["total"] if want_energy else 0.0
    return energy, pose
