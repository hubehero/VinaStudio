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

    if params.ligand_path:
        ligand_path = params.ligand_path
    else:
        # The CLI takes a file; writing the inline string here keeps the caller's
        # contract intact rather than making it a special case upstream.
        inline = target / "ligand.pdbqt"
        inline.write_text(params.ligand_pdbqt_string or "", encoding="utf-8")
        ligand_path = str(inline)

    command = build_command(params, out_pdbqt, ligand_path, binary)

    log.info("starting CLI docking: scoring=%s exhaustiveness=%d",
             params.scoring, params.exhaustiveness)

    start = time.monotonic()
    try:
        completed = subprocess.run(command, stderr=subprocess.PIPE, text=True, check=False)
    except PermissionError as exc:
        raise RuntimeError(f"{binary} is not executable: {exc}") from exc
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise RuntimeError(
            f"vina exited with {completed.returncode}"
            + (f": {detail[-1]}" if detail else "")
        )

    return result_from_poses(out_pdbqt, elapsed_ms)
