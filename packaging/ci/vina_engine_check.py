"""Prove the docking engine actually runs *here* — including on Windows.

The release tree deliberately does not ship the test suite (`.gitignore` excludes
it), so CI cannot run pytest against it. This script is the substitute, and it is
the only evidence behind the claim "the engine works on this platform": it docks
the 1iep gold standard through the command-line backend and checks the result
against the same regime the Linux tests use.

It needs no GUI and no Qt: the CLI backend is a subprocess, which is exactly why
the scientific verification can run on `windows-latest`, where the `vina` Python
module cannot be installed at all.

Run from the repository root:

    python packaging/ci/vina_engine_check.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# The package is imported from the checkout, not installed: pulling the whole
# dependency set (PySide6 and friends) just to dock would defeat the point of a
# light, GUI-free check.
sys.path.insert(0, str(REPO_ROOT))

from vinastudio.config import RESOURCES_DIR  # noqa: E402
from vinastudio.core.docking import DockingParams  # noqa: E402
from vinastudio.core.engines import backend_report  # noqa: E402
from vinastudio.core.engines.vina_cli import cli_path, run_docking_cli  # noqa: E402

SAMPLE = RESOURCES_DIR / "sample" / "1iep"
RECEPTOR = SAMPLE / "1iep_receptor.pdbqt"
LIGAND = SAMPLE / "1iep_ligand.pdbqt"

#: The project's gold standard box (AGENTS.md), and the bar its Linux tests use.
CENTER = (15.190, 53.903, 16.917)
SIZE = (20.0, 20.0, 20.0)
EXHAUSTIVENESS = 8
BEST_AFFINITY_CEILING = -9.0


def fail(message: str) -> None:
    print(f"FAIL  {message}")
    raise SystemExit(1)


def ensure_samples() -> None:
    if RECEPTOR.is_file() and LIGAND.is_file():
        print(f"ok    gold-standard samples present: {SAMPLE}")
        return
    print("..    fetching the 1iep samples (checksum-verified)")
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "fetch_samples.py")],
        cwd=str(REPO_ROOT),
        check=False,
    )
    if completed.returncode != 0 or not RECEPTOR.is_file():
        fail("could not obtain the 1iep samples — the check needs them to run")


def ensure_binary() -> Path:
    """The engine binary, fetched (checksum-verified) if this checkout lacks it."""
    try:
        binary = cli_path()
    except FileNotFoundError:
        print("..    fetching the official Vina binary for this platform")
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "fetch_vina_cli.py")],
            cwd=str(REPO_ROOT),
            check=False,
        )
        try:
            binary = cli_path()
        except FileNotFoundError as exc:
            fail(f"{exc}")
    print(f"ok    Vina binary: {binary}")
    return binary


def main() -> None:
    print(f"platform: {sys.platform}   python: {sys.version.split()[0]}")

    ensure_binary()

    report = backend_report()
    print(f"ok    backend here: {report.get('backend')} (reason: {report.get('reasonCode')})")

    ensure_samples()

    params = DockingParams(
        receptor_path=str(RECEPTOR),
        ligand_path=str(LIGAND),
        center=CENTER,
        size=SIZE,
        scoring="vina",
        exhaustiveness=EXHAUSTIVENESS,
        n_poses=9,
        energy_range=3.0,
        seed=42,
        verbosity=0,
    )

    with tempfile.TemporaryDirectory(prefix="vinastudio-engine-check-") as scratch:
        result = run_docking_cli(params, scratch)
        pose_file = Path(scratch) / "poses.pdbqt"
        if not pose_file.is_file():
            fail("the engine reported success but wrote no poses")

    print(f"ok    docked in {result.elapsed_ms} ms, {len(result.poses)} pose(s)")
    print(f"      best affinity: {result.best_affinity:.3f} kcal/mol")

    if not result.poses:
        fail("no poses were parsed from the output")
    if result.best_affinity > BEST_AFFINITY_CEILING:
        fail(
            f"best affinity {result.best_affinity:.3f} is above the {BEST_AFFINITY_CEILING} "
            "ceiling the Linux tests use — the engine is not reproducing here"
        )
    if not result.poses_sdf.strip():
        fail("poses did not convert to SDF — the Meeko/RDKit stack is not working here")

    print("PASS  the docking engine reproduces the gold-standard regime on this platform")


if __name__ == "__main__":
    main()
