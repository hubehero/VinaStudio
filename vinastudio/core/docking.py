"""Thin wrapper around the ``vina`` Python API for a single docking run.

The wrapper is a stateless function: it creates a ``Vina`` instance, configures
it, calls ``dock()``, and returns structured results. All heavy lifting happens
in the caller's process (which is a spawned child — see ``worker.py``).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DockingParams:
    """Everything the Vina API needs for one docking run."""

    receptor_path: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    ligand_path: str | None = None
    ligand_pdbqt_string: str | None = None
    flex_pdbqt_path: str | None = None
    scoring: str = "vina"
    exhaustiveness: int = 8
    n_poses: int = 20
    energy_range: float = 3.0
    min_rmsd: float = 1.0
    max_evals: int = 0
    cpu: int = 0
    seed: int = 0
    no_refine: bool = False
    verbosity: int = 1
    spacing: float = 0.375
    force_even_voxels: bool = False
    weights: list[float] | None = None
    map_paths: list[str] | None = None


@dataclass(slots=True)
class PoseResult:
    index: int
    affinity: float
    rmsd_lower: float
    rmsd_upper: float


@dataclass(slots=True)
class DockingResult:
    poses: list[PoseResult] = field(default_factory=list)
    best_affinity: float = 0.0
    n_poses: int = 0
    elapsed_ms: int = 0
    poses_pdbqt: str = ""
    poses_sdf: str = ""


def run_docking(params: DockingParams, output_dir: str) -> DockingResult:
    """Execute a full docking run and return structured results.

    This function runs inside a **spawned child process** so that killing the
    process is the only cancellation mechanism — Vina has no interruption API.
    """
    from vina import Vina  # type: ignore[import-untyped]

    t0 = time.monotonic()

    v = Vina(sf_name=params.scoring, cpu=params.cpu, seed=params.seed,
             no_refine=params.no_refine, verbosity=params.verbosity)

    v.set_receptor(
        rigid_pdbqt_filename=params.receptor_path,
        flex_pdbqt_filename=params.flex_pdbqt_path or None,
    )

    if params.ligand_pdbqt_string:
        v.set_ligand_from_string(params.ligand_pdbqt_string)
    elif params.ligand_path:
        v.set_ligand_from_file(params.ligand_path)
    else:
        raise ValueError("either ligand_path or ligand_pdbqt_string must be provided")

    if params.map_paths:
        # The caller supplies the prefix Vina's own map files are named after;
        # deriving it from a file name cannot work, because a prefix may itself
        # contain the separator this used to split on.
        v.load_maps(params.map_paths[0])
    else:
        v.compute_vina_maps(
            center=list(params.center),
            box_size=list(params.size),
            spacing=params.spacing,
            force_even_voxels=params.force_even_voxels,
        )

    if params.weights is not None:
        v.set_weights(params.weights)

    log.info(
        "starting docking: scoring=%s exhaustiveness=%d n_poses=%d",
        params.scoring, params.exhaustiveness, params.n_poses,
    )

    v.dock(
        exhaustiveness=params.exhaustiveness,
        n_poses=params.n_poses,
        min_rmsd=params.min_rmsd,
        max_evals=params.max_evals,
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    out_pdbqt = Path(output_dir) / "poses.pdbqt"
    v.write_poses(
        str(out_pdbqt),
        n_poses=params.n_poses,
        energy_range=params.energy_range,
        overwrite=True,
    )

    # Parse the written PDBQT to extract affinities and RMSD values from
    # REMARK VINA RESULT lines.  The Vina.energies() API does not return RMSD.
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    poses: list[PoseResult] = []
    if out_pdbqt.exists():
        pdbqt_text = out_pdbqt.read_text(encoding="utf-8", errors="replace")
        doc = parse_pdbqt(pdbqt_text)
        for pose in doc.poses:
            poses.append(PoseResult(
                index=pose.index,
                affinity=pose.energy or 0.0,
                rmsd_lower=pose.rmsd_lower_bound or 0.0,
                rmsd_upper=pose.rmsd_upper_bound or 0.0,
            ))

    best = min((p.affinity for p in poses), default=0.0) if poses else 0.0

    result = DockingResult(
        poses=poses,
        best_affinity=best,
        n_poses=len(poses),
        elapsed_ms=elapsed_ms,
        poses_pdbqt=out_pdbqt.read_text(encoding="utf-8", errors="replace") if out_pdbqt.exists() else "",
    )

    # Convert to SDF via Meeko
    try:
        from vinastudio.core.chem.export import poses_to_sdf
        sdf_result = poses_to_sdf(result.poses_pdbqt, title_prefix="pose")
        result.poses_sdf = sdf_result.sdf
    except (ImportError, RuntimeError, ValueError) as exc:
        log.warning("SDF export failed: %s", exc)

    return result
