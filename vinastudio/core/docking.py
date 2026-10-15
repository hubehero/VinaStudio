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
    map_prefix: str | None = None
    """Pre-computed map prefix (from ``precompute_vina_maps``). Overrides ``map_paths``."""
    engine: str = "vina"
    """Docking engine: ``"vina"`` (default CPU), or ``"unidock"`` (GPU, future)."""


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

    if params.map_prefix:
        # Pre-computed maps from ``precompute_vina_maps`` — a single prefix.
        v.load_maps(params.map_prefix)
    elif params.map_paths:
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

    return result_from_poses(out_pdbqt, elapsed_ms)


def result_from_poses(out_pdbqt: Path, elapsed_ms: int) -> DockingResult:
    """Assemble a :class:`DockingResult` from a written poses file.

    Shared by both backends deliberately: the Python API and the CLI write the
    same PDBQT, and a second copy of this assembly is exactly how the two would
    start disagreeing about affinities, pose counts or the SDF conversion.
    """
    # Affinities and RMSD come from the ``REMARK VINA RESULT`` lines; the
    # ``Vina.energies()`` API does not return RMSD at all.
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    text = out_pdbqt.read_text(encoding="utf-8", errors="replace") if out_pdbqt.exists() else ""

    poses: list[PoseResult] = []
    if text:
        for pose in parse_pdbqt(text).poses:
            poses.append(PoseResult(
                index=pose.index,
                affinity=pose.energy or 0.0,
                rmsd_lower=pose.rmsd_lower_bound or 0.0,
                rmsd_upper=pose.rmsd_upper_bound or 0.0,
            ))

    result = DockingResult(
        poses=poses,
        best_affinity=min((p.affinity for p in poses), default=0.0) if poses else 0.0,
        n_poses=len(poses),
        elapsed_ms=elapsed_ms,
        poses_pdbqt=text,
    )

    try:
        from vinastudio.core.chem.export import poses_to_sdf

        result.poses_sdf = poses_to_sdf(result.poses_pdbqt, title_prefix="pose").sdf
    except (ImportError, RuntimeError, ValueError) as exc:
        log.warning("SDF export failed: %s", exc)

    return result


def precompute_vina_maps(
    receptor_path: str,
    flex_pdbqt_path: str | None,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    scoring: str = "vina",
    spacing: float = 0.375,
    force_even_voxels: bool = False,
    output_dir: str = "",
) -> str:
    """Pre-compute Vina affinity maps once, returning the map prefix for reuse.

    In batch mode the maps are identical for every ligand, so computing
    them once and passing the prefix to subsequent ``run_docking`` calls
    avoids redundant grid calculations.

    Returns the prefix path that ``Vina.load_maps()`` expects.
    """
    from vina import Vina  # type: ignore[import-untyped]

    v = Vina(sf_name=scoring, cpu=0, seed=0, verbosity=0)
    v.set_receptor(
        rigid_pdbqt_filename=receptor_path,
        flex_pdbqt_filename=flex_pdbqt_path or None,
    )
    v.compute_vina_maps(
        center=list(center),
        box_size=list(size),
        spacing=spacing,
        force_even_voxels=force_even_voxels,
    )

    prefix = str(Path(output_dir) / "maps")
    v.write_maps(prefix)
    log.info("pre-computed Vina maps: %s", prefix)

    return prefix
