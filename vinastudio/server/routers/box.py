"""Search-box endpoints: autobox, live metrics, config.txt interop, and map export."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from vinastudio.core.box import Box, autobox_from_file
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import resolve_within, workspace_root
from vinastudio.schemas.box import (
    AutoboxFromResiduesRequest,
    AutoboxRequest,
    AutoboxResponse,
    BoxMetrics,
    BoxSpec,
    ConfigText,
    WriteMapsRequest,
    WriteMapsResponse,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/box", tags=["box"])

#: Above this many voxels the affinity maps stop being a convenience: memory and
#: grid-computation time grow with the volume, so the panel says so up front.
VOXEL_WARNING_THRESHOLD = 4_000_000


def _warnings(box: Box) -> list[str]:
    """Things the user should know before running docking with this box."""
    warnings: list[str] = []

    odd_axes = [
        axis for axis, count in zip("xyz", box.voxels, strict=True) if count % 2 == 1
    ]
    if odd_axes and not box.force_even_voxels:
        warnings.append(
            f"the voxel count is odd along {'/'.join(odd_axes)}, and write_maps "
            "refuses that; enable force_even_voxels to round it up"
        )

    total_voxels = box.voxels[0] * box.voxels[1] * box.voxels[2]
    if total_voxels > VOXEL_WARNING_THRESHOLD:
        warnings.append(
            f"the box holds {total_voxels / 1e6:.1f} million voxels; grid computation "
            "time and memory grow with the enclosed volume"
        )

    return warnings


def _metrics_from_box(box: Box) -> BoxMetrics:
    """Present a validated box together with everything derived from it."""
    lower, upper = box.limits
    return BoxMetrics(
        center=box.center,
        size=box.size,
        spacing=box.spacing,
        forceEvenVoxels=box.force_even_voxels,
        voxels=list(box.voxels),
        gridPoints=list(box.grid_points),
        volume=box.volume,
        canWriteMaps=box.can_write_maps,
        limits=[list(lower), list(upper)],
        warnings=_warnings(box),
    )


def _as_box(spec: BoxSpec) -> Box:
    """Build a box from a request, letting ``Box`` do the validating."""
    return Box(
        center=spec.center,
        size=spec.size,
        spacing=spec.spacing,
        force_even_voxels=spec.forceEvenVoxels,
    )


@router.post("/metrics", response_model=BoxMetrics)
def measure(spec: BoxSpec) -> BoxMetrics:
    """Derived quantities for a box, called as the panel is edited.

    A round trip per edit is cheap on loopback and buys a single definition of
    the voxel and grid-point rules.
    """
    return _metrics_from_box(_as_box(spec))


@router.post("/from-ligand", response_model=AutoboxResponse)
def from_ligand(request: AutoboxRequest) -> AutoboxResponse:
    """Derive the box from a ligand, a pose, or any single-molecule file."""
    box, points = autobox_from_file(
        request.path,
        extend=request.extend,
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
        include_hydrogens=request.includeHydrogens,
    )
    log.info("autobox from %s: %d atoms -> %.1f A box", request.path, points, box.size[0])
    return AutoboxResponse(box=_metrics_from_box(box), points=points, source=request.path)


@router.post("/from-residues", response_model=AutoboxResponse)
def from_residues(request: AutoboxFromResiduesRequest) -> AutoboxResponse:
    """Derive the box from a residue selection, such as the binding-site residues."""
    box, points = autobox_from_file(
        request.path,
        extend=request.extend,
        residues=tuple(request.residues),
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
        include_hydrogens=request.includeHydrogens,
    )
    log.info(
        "autobox from %s residues %s: %d atoms",
        request.path,
        ",".join(request.residues) or "(all)",
        points,
    )
    return AutoboxResponse(box=_metrics_from_box(box), points=points, source=request.path)


@router.post("/to-config", response_model=ConfigText)
def to_config(spec: BoxSpec) -> ConfigText:
    """Serialise a box as a Vina ``config.txt`` fragment."""
    return ConfigText(text=_as_box(spec).to_config())


@router.post("/from-config", response_model=BoxMetrics)
def from_config(payload: ConfigText) -> BoxMetrics:
    """Read a box out of a Vina ``config.txt``.

    Unknown keys are ignored on purpose: the same file describes a whole docking
    run, and refusing it would make the feature useless for its main purpose.
    """
    return _metrics_from_box(Box.from_config(payload.text))


@router.post("/write-maps", response_model=WriteMapsResponse)
def write_maps(request: WriteMapsRequest) -> WriteMapsResponse:
    """Compute and write affinity maps for the given receptor and box.

    Vina generates maps for all 22 atom types when no ligand is loaded,
    which is what batch screening and AutoDock4 need.
    """
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    prefix = Path(request.outputPrefix)
    # The prefix arrives in the request body; without this the endpoint would
    # create directories and write maps anywhere the process can reach.
    try:
        prefix = resolve_within(workspace_root(), request.outputPrefix)
    except ValueError as exc:
        raise InvalidInputError(
            f"output prefix must stay inside the run root: {request.outputPrefix}"
        ) from exc
    prefix.parent.mkdir(parents=True, exist_ok=True)

    from vina import Vina  # type: ignore[import-untyped]

    v = Vina(sf_name="vina", cpu=0, verbosity=0)
    v.set_receptor(rigid_pdbqt_filename=str(receptor))
    v.compute_vina_maps(
        center=list(request.center),
        box_size=list(request.size),
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
    )

    prefix_str = str(prefix)
    v.write_maps(
        map_prefix_filename=prefix_str,
        gpf_filename="NULL",
        fld_filename="NULL",
        receptor_filename="NULL",
        overwrite=True,
    )

    # Collect written map files
    map_files = sorted(str(p) for p in prefix.parent.glob(f"{prefix.name}*.*") if p.suffix in (".map", ".Map"))
    log.info("wrote %d map files to %s", len(map_files), prefix)

    return WriteMapsResponse(maps=map_files)
