"""Docking endpoints: start, status, cancel, list jobs."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from vinastudio import __version__
from vinastudio.config import (
    NATIVE_MAP_SCORING,
    SCORING_WEIGHT_COUNT,
    max_map_cells,
    max_upload_bytes,
)
from vinastudio.core.box import Box, ensure_box_contains_receptor
from vinastudio.core.chem.ifp import (
    CONTACT_TYPES,
    butina_clustering,
    fingerprint,
    parse_ligand_sdf,
    parse_receptor_atoms,
    residue_columns,
    tanimoto,
)
from vinastudio.core.docking import DockingParams
from vinastudio.core.engines import CLI_BACKEND, resolve_backend
from vinastudio.core.engines.vina_cli import optimize_cli, randomize_cli, score_cli
from vinastudio.core.errors import (
    EngineCapabilityError,
    InvalidInputError,
    JobNotFoundError,
    brief_error,
)
from vinastudio.core.paths import (
    ANALYSIS_CACHE_FILENAME,
    BATCH_RESULTS_CSV_FILENAME,
    JOB_LOG_FILENAME,
    POSES_SDF_FILENAME,
    job_dir,
    slugify,
    workspace_root,
)
from vinastudio.core.report import render_report, svg_is_safe
from vinastudio.schemas.docking import (
    BatchDockingRequest,
    BatchJobCreated,
    BatchJobResult,
    BatchJobStatus,
    BatchLigandItem,
    BatchLigandProgress,
    BatchLigandResult,
    CitationResponse,
    ClusterItem,
    ClusterRequest,
    ClusterResponse,
    DockingDefaultsResponse,
    DockingJobCreated,
    DockingJobResult,
    DockingJobStatus,
    DockingJobSummary,
    DockingRequest,
    EnsembleDockingRequest,
    EnsembleRow,
    ExportBundleRequest,
    ExportPoseRequest,
    ExportPoseResponse,
    IfpClusterRow,
    IfpFingerprint,
    IfpJobRequest,
    IfpJobResponse,
    IfpResidue,
    ImportBundleResponse,
    OptimizeRequest,
    OptimizeResponse,
    PoseFindingModel,
    PoseInfo,
    PoseValidationItem,
    RandomizeRequest,
    RandomizeResponse,
    RmsdRequest,
    RmsdResponse,
    ScoreRequest,
    ScoreResponse,
    ValidatePosesRequest,
    ValidatePosesResponse,
    VinaInfoResponse,
)
from vinastudio.schemas.preparation import Artifact
from vinastudio.server.job_manager import JobState
from vinastudio.server.job_manager import batch_results_csv_text as _batch_csv_text
from vinastudio.server.job_manager import manager as job_manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/docking", tags=["docking"])

#: Result bundle v1 is self-contained enough to rebuild a read-only result:
#: the sanitized job payload, the pose SDF, and the log.  Optional members
#: mirror the export dialog.  The import endpoint accepts only these names.
BUNDLE_FORMAT = "vinastudio-result-bundle"
BUNDLE_VERSION = 1
BUNDLE_REQUIRED = frozenset({"manifest.json", "job.json", "poses.sdf"})
BUNDLE_OPTIONAL = frozenset(
    {"job.log", "config.txt", "results.csv", "report.html", "interactions-2d.svg"}
)
BUNDLE_MEMBERS = BUNDLE_REQUIRED | BUNDLE_OPTIONAL
BUNDLE_MAX_ENTRIES = 64
_BUNDLE_INLINE_KEYS = frozenset({
    "ligandPdbqtString", "receptorPdbqtString", "pdbqtString",
    "ligand_pdbqt_string", "receptor_pdbqt_string", "pdbqt_string",
})

#: Download tokens map to server-generated files; the URL never carries a
#: path, so a request cannot express a filesystem location.  The small cap
#: means the mapping is a convenience for the current session, not storage —
#: the file itself lives on in exports/result-bundles/.
_BUNDLE_DOWNLOADS: dict[str, Path] = {}
_BUNDLE_DOWNLOAD_LIMIT = 128

# Interactive score/optimize/randomize build affinity maps in the API process.
# One in-flight map set is already ~150 MB at the default 1iep box; concurrent
# calls could otherwise take down the process that owns every running job.
_INTERACTIVE_MAPS = threading.BoundedSemaphore(1)
_INTERACTIVE_MAX_CELLS = max_map_cells()


def _validate_box(
    receptor_path: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    *,
    spacing: float = 0.375,
    force_even_voxels: bool = False,
) -> None:
    """Reject a box that cannot score anything before a job is spawned."""
    ensure_box_contains_receptor(
        receptor_path,
        Box(
            center=center,
            size=size,
            spacing=spacing,
            force_even_voxels=force_even_voxels,
        ),
    )


@router.get("/defaults", response_model=DockingDefaultsResponse)
def get_defaults() -> DockingDefaultsResponse:
    """Return default docking parameters for the UI form."""
    return DockingDefaultsResponse()


@router.get("/info", response_model=VinaInfoResponse)
def get_info() -> VinaInfoResponse:
    """Return the installed Vina/CLI metadata and capabilities."""
    import multiprocessing
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as package_version

    from vinastudio.core.engines import CLI_BACKEND, resolve_backend

    try:
        engine_version = package_version("vina")
    except PackageNotFoundError:
        try:
            engine_version = "vina-cli" if resolve_backend() == CLI_BACKEND else "unknown"
        except (ValueError, RuntimeError):
            engine_version = "unavailable"
    cpu_count = multiprocessing.cpu_count()
    return VinaInfoResponse(
        version=engine_version,
        supportedScoringFunctions=list(SCORING_WEIGHT_COUNT.keys()),
        cpuCount=cpu_count,
        maxCPUs=cpu_count,
    )


@router.get("/cite", response_model=CitationResponse)
def get_citation(scoring: str = "vina") -> CitationResponse:
    """Return citation text for the selected scoring function."""

    if scoring not in SCORING_WEIGHT_COUNT:
        raise InvalidInputError(f"unknown scoring function: {scoring}")

    citations = {
        "vina": CitationResponse(
            function="vina",
            citation="Trott, O. & Olson, A. J. AutoDock Vina: Improving the speed and "
            "accuracy of docking with a new scoring function, efficient optimization, "
            "and multithreading. J. Comput. Chem. 31, 455-461 (2010).",
        ),
        "ad4": CitationResponse(
            function="ad4",
            citation="Morris, G. M. et al. AutoDock4 and AutoDockTools4: Automated "
            "docking with selective receptor flexibility. J. Comput. Chem. 30, "
            "2785-2791 (2009).",
        ),
        "vinardo": CitationResponse(
            function="vinardo",
            citation="Quiroga, R. & Villarreal, M. A. Vinardo: A Scoring Function "
            "Based on Autodock Vina Improves Scoring, Docking, and Virtual "
            "Screening. PLoS ONE 11, e0155183 (2016).",
        ),
    }

    return citations[scoring]


@router.post("/start", response_model=DockingJobCreated)
def start_docking(request: DockingRequest) -> DockingJobCreated:
    """Start a new docking job in a spawned child process."""
    # Validate input files exist
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    # Ligand: either a path or an inline string must be provided
    if not request.ligandPath and not request.ligandPdbqtString:
        raise InvalidInputError("either ligandPath or ligandPdbqtString must be provided")
    if request.ligandPath:
        ligand = Path(request.ligandPath)
        if not ligand.exists():
            raise InvalidInputError(f"ligand file not found: {request.ligandPath}")

    if request.flexReceptorPath:
        flex = Path(request.flexReceptorPath)
        if not flex.exists():
            raise InvalidInputError(f"flex receptor file not found: {request.flexReceptorPath}")

    # Validate AD4 needs maps
    if request.scoring == "ad4" and not request.mapPaths:
        raise InvalidInputError("ad4 scoring requires mapPaths")
    if request.mapPaths:
        if len(request.mapPaths) != 1:
            raise InvalidInputError("mapPaths must contain one AutoGrid4 map prefix")
        prefix = Path(request.mapPaths[0])
        if prefix.suffix.lower() == ".map":
            raise InvalidInputError(
                "mapPaths expects the AutoGrid4 prefix, not an individual .map file"
            )
    if not request.mapPaths:
        _validate_box(request.receptorPath, request.center, request.size)

    params = {
        "receptor_path": request.receptorPath,
        "ligand_path": request.ligandPath,
        "ligand_pdbqt_string": request.ligandPdbqtString,
        "center": list(request.center),
        "size": list(request.size),
        "scoring": request.scoring,
        "exhaustiveness": request.exhaustiveness,
        "n_poses": request.nPoses,
        "energy_range": request.energyRange,
        "min_rmsd": request.minRmsd,
        "max_evals": request.maxEvals,
        "cpu": request.cpu,
        "seed": request.seed,
        "no_refine": request.noRefine,
        "verbosity": request.verbosity,
        "spacing": request.spacing,
        "force_even_voxels": request.forceEvenVoxels,
        "weights": request.weights,
        "map_paths": request.mapPaths,
        "flex_pdbqt_path": request.flexReceptorPath,
        "engine": request.engine,
        "preparation": request.preparation,
    }

    job_id = job_manager.start_job(params)
    return DockingJobCreated(jobId=job_id, status="queued")


@router.post("/ensemble", response_model=DockingJobCreated)
def start_ensemble_docking(request: EnsembleDockingRequest) -> DockingJobCreated:
    """Dock one ligand into several receptor conformations (TASK-60-B).

    Conformers must share the coordinate frame; the same box is used for each.
    This is ensemble docking, not induced fit. AD4 is rejected because maps are
    per-receptor and the current request has one map prefix.
    """
    if len(request.receptors) < 2:
        raise InvalidInputError("ensemble docking requires at least two receptors")
    if request.scoring == "ad4":
        raise InvalidInputError(
            "ensemble docking currently supports vina/vinardo; AD4 maps are per-receptor"
        )
    if not request.ligandPath and not request.ligandPdbqtString:
        raise InvalidInputError("either ligandPath or ligandPdbqtString must be provided")

    for receptor in request.receptors:
        if not Path(receptor.path).exists():
            raise InvalidInputError(f"receptor file not found: {receptor.path}")
        if receptor.flexPath and not Path(receptor.flexPath).exists():
            raise InvalidInputError(f"flex receptor file not found: {receptor.flexPath}")
        _validate_box(receptor.path, request.center, request.size)
    if request.ligandPath and not Path(request.ligandPath).exists():
        raise InvalidInputError(f"ligand file not found: {request.ligandPath}")

    job_id = job_manager.start_ensemble_job({
        "receptors": [receptor.model_dump() for receptor in request.receptors],
        "ligand_path": request.ligandPath,
        "ligand_pdbqt_string": request.ligandPdbqtString,
        "center": list(request.center),
        "size": list(request.size),
        "scoring": request.scoring,
        "exhaustiveness": request.exhaustiveness,
        "n_poses": request.nPoses,
        "energy_range": request.energyRange,
        "min_rmsd": request.minRmsd,
        "max_evals": request.maxEvals,
        "cpu": request.cpu,
        "seed": request.seed,
        "no_refine": request.noRefine,
        "verbosity": request.verbosity,
        "spacing": request.spacing,
        "force_even_voxels": request.forceEvenVoxels,
        "weights": request.weights,
        "map_paths": request.mapPaths,
        "engine": request.engine,
        "label": "ensemble",
    })
    return DockingJobCreated(jobId=job_id, status="queued")


@router.post("/batch", response_model=BatchJobCreated)
def batch_docking(request: BatchDockingRequest) -> BatchJobCreated:
    """Start a batch docking job in a spawned child process."""
    if request.scoring == "ad4":
        raise InvalidInputError(
            "batch docking supports vina/vinardo; AD4 maps are not part of this request"
        )
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    ligands = request.ligands
    if request.selectionId:
        from vinastudio.core.catalog import db as catalog_db
        from vinastudio.core.catalog import store as catalog_store

        with catalog_db.transaction(catalog_db.catalog_path()) as conn:
            selection = catalog_store.get_selection(conn, request.selectionId)
            if selection is None:
                raise InvalidInputError(
                    f"selection not found: {request.selectionId}"
                )
            members = catalog_store.selection_entries(conn, request.selectionId)
            expected = int(selection["memberCount"])
            if selection.get("stale") or len(members) != expected:
                raise InvalidInputError(
                    f"selection {request.selectionId} is stale ({len(members)}/{expected} "
                    "members); recreate the selection before running it"
                )
        params_label = str(selection.get("name") or request.selectionId)
        ligands = []
        for member in members:
            prepared = member.get("prepared_path")
            source = member.get("source_path")
            if prepared and Path(str(prepared)).is_file():
                ligands.append(BatchLigandItem(
                    ligandPath=str(prepared),
                    label=str(member["name"]),
                ))
            elif source and Path(str(source)).is_file():
                # The batch worker prepares this selected source lazily; no
                # silent drop and no full-library pre-preparation.
                ligands.append(BatchLigandItem(
                    ligandPath=str(source),
                    label=str(member["name"]),
                    prepare=True,
                ))
            else:
                raise InvalidInputError(
                    f"selected molecule {member['name']} has no usable source or PDBQT"
                )
    if not ligands:
        raise InvalidInputError("ligands list is empty")
    _validate_box(request.receptorPath, request.center, request.size)

    params = {
        "receptor_path": request.receptorPath,
        "flex_pdbqt_path": request.flexReceptorPath,
        "center": list(request.center),
        "size": list(request.size),
        "ligands": [
            {
                "ligandPath": lig.ligandPath,
                "ligandPdbqtString": lig.ligandPdbqtString,
                "label": lig.label,
                "prepare": lig.prepare,
            }
            for lig in ligands
        ],
        "scoring": request.scoring,
        "exhaustiveness": request.exhaustiveness,
        "n_poses": request.nPoses,
        "energy_range": request.energyRange,
        "min_rmsd": request.minRmsd,
        "cpu": request.cpu,
        "seed": request.seed,
        "no_refine": request.noRefine,
        "weights": request.weights,
        "engine": request.engine,
    }
    # `extra="forbid"` rejected the key up here; the worker pool picks it up
    # only when the client sent it (absent = server default, TASK-14 §4.2).
    if request.selectionId:
        params["selection_id"] = request.selectionId
        params["label"] = params_label
    if request.parallelism is not None:
        params["parallelism"] = request.parallelism

    job_id = job_manager.start_batch_job(params)
    return BatchJobCreated(jobId=job_id, status="queued", total=len(ligands))


def _summary_best_affinity(state: JobState) -> float | None:
    """Best score for the jobs list; None until something was scored.

    ``JobState.best_affinity`` tracks single jobs only, so a batch reports
    its best completed ligand from the ranking rows instead.
    """
    if state.status != "completed":
        return None
    if not state.is_batch:
        return state.best_affinity
    scored = [
        row["bestAffinity"]
        for row in state.batch_results
        if row.get("bestAffinity") is not None
    ]
    return min(scored) if scored else None


@router.get("/jobs", response_model=list[DockingJobSummary])
def list_jobs() -> list[DockingJobSummary]:
    """Return all known jobs."""
    jobs = job_manager.list_jobs()
    return [
        DockingJobSummary(
            jobId=j.job_id,
            status=j.status,
            progress=j.progress,
            stage=j.stage,
            scoring=j.scoring,
            elapsedMs=j.elapsed_ms,
            createdAt=j.created_at,
            label=j.label,
            bestAffinity=_summary_best_affinity(j),
            isBatch=j.is_batch,
            isEnsemble=j.is_ensemble,
        )
        for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)
    ]


@router.get("/jobs/{job_id}", response_model=DockingJobStatus)
def get_job_status(job_id: str) -> DockingJobStatus:
    """Return the current state of a docking job."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")

    return DockingJobStatus(
        jobId=state.job_id,
        status=state.status,
        progress=state.progress,
        stage=state.stage,
        log=state.log[-100:],
        error=state.error,
        elapsedMs=state.elapsed_ms,
    )


@router.get("/jobs/{job_id}/result", response_model=DockingJobResult)
def get_job_result(job_id: str) -> DockingJobResult:
    """Return completed job results with poses."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    # The inline ligand string is dropped on the way out: it is the only large
    # field and it is already reflected by the poses. Everything else is the
    # request the job actually ran with (report "Methods" reads these).
    params = {
        key: value
        for key, value in (state.params or {}).items()
        if key != "ligand_pdbqt_string"
    }
    return DockingJobResult(
        jobId=state.job_id,
        status="completed",
        poses=state.poses,
        bestAffinity=state.best_affinity,
        posesPdbqt=state.poses_pdbqt,
        posesSdf=state.poses_sdf,
        nPoses=state.n_poses,
        scoring=state.scoring,
        elapsedMs=state.elapsed_ms or 0,
        artifacts=state.artifacts,
        params=params,
        isEnsemble=state.is_ensemble,
        bestReceptor=state.best_receptor,
        ensembleRows=[EnsembleRow(**row) for row in state.ensemble_results],
    )


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, str]:
    """Cancel a running job by killing its worker process."""
    success = job_manager.cancel_job(job_id)
    if not success:
        raise JobNotFoundError(f"job {job_id} not found or not running")
    return {"status": "cancelled", "jobId": job_id}


@router.post("/jobs/{job_id}/validate", response_model=ValidatePosesResponse)
def validate_job_poses(job_id: str, request: ValidatePosesRequest) -> ValidatePosesResponse:
    """Run the geometric health-check on a completed job's poses.

    Report-only: never re-docks or edits coordinates. Box and reference are
    optional — omitting them skips ``out_of_box`` / the four reference-relative
    checks rather than failing the request.
    """
    from vinastudio.core.chem.pose_validation import (
        THRESHOLDS,
        validate_poses,
        worst_severity,
    )

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")
    if not state.poses_sdf:
        raise InvalidInputError("job has no pose SDF to validate")

    box = None
    if request.center is not None and request.size is not None:
        from vinastudio.core.box import Box

        box = Box(center=request.center, size=request.size)

    reference: str | Path | None = None
    if request.referenceSdfPath:
        ref_path = Path(request.referenceSdfPath)
        if not ref_path.exists():
            raise InvalidInputError(f"reference SDF not found: {request.referenceSdfPath}")
        reference = ref_path

    try:
        per_pose = validate_poses(
            state.poses_sdf,
            reference,
            box=box,
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc

    if request.poseIndex is not None:
        idx = request.poseIndex - 1
        if idx < 0 or idx >= len(per_pose):
            raise InvalidInputError(
                f"pose {request.poseIndex} does not exist; the result has {len(per_pose)} poses"
            )
        selected = [(request.poseIndex, per_pose[idx])]
    else:
        selected = list(enumerate(per_pose, start=1))

    poses = [
        PoseValidationItem(
            poseIndex=index,
            findings=[
                PoseFindingModel(
                    code=f.code,
                    severity=f.severity,
                    messageKey=f.message_key,
                    detail=f.detail,
                )
                for f in findings
            ],
            worstSeverity=worst_severity(findings),
        )
        for index, findings in selected
    ]

    checks_run = sorted(
        request.enabled
        if request.enabled is not None
        else (
            "internal_clash",
            "bond_length_outlier",
            "angle_outlier",
            "planarity_break",
            "chirality_flip",
            "out_of_box",
        )
    )
    if box is None and "out_of_box" in checks_run:
        checks_run.remove("out_of_box")
    if reference is None:
        checks_run = [
            c for c in checks_run if c not in {
                "bond_length_outlier",
                "angle_outlier",
                "planarity_break",
                "chirality_flip",
            }
        ]

    return ValidatePosesResponse(
        jobId=job_id,
        poses=poses,
        thresholds=dict(THRESHOLDS),
        checksRun=checks_run,
    )


@router.post("/jobs/{job_id}/rmsd", response_model=RmsdResponse)
def rmsd_against_reference(job_id: str, request: RmsdRequest) -> RmsdResponse:
    """Heavy-atom RMSD of each pose against a co-crystal reference ligand.

    Symmetry-corrected, fixed-frame (``CalcRMS``); report-only. A reference that is a
    different chemical structure returns ``structureMatch=False`` with empty
    ``values`` — a warning, never a rejection.
    """
    from vinastudio.core.chem.rmsd import (
        reference_matches_poses,
        rmsd_vs_reference,
        success_rate,
    )

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")
    if not state.poses_sdf:
        raise InvalidInputError("job has no pose SDF to compare")

    reference = request.referencePath or request.referencePdbqt
    if reference is None:
        raise InvalidInputError("referencePath or referencePdbqt is required")
    ref_path = Path(reference)
    if not ref_path.exists():
        raise InvalidInputError(f"reference not found: {reference}")

    structure_match = reference_matches_poses(state.poses_sdf, ref_path)
    if structure_match is False:
        # Comparing different chemical structures would report a meaningless
        # RMSD (or fail atom-count checks) — warn, don't reject, don't compute.
        return RmsdResponse(
            jobId=job_id,
            values=[],
            threshold=request.threshold,
            successRate=0.0,
            structureMatch=False,
        )

    try:
        values = rmsd_vs_reference(state.poses_sdf, ref_path)
    except (ValueError, RuntimeError) as exc:
        raise InvalidInputError(f"RMSD computation failed: {exc}") from exc

    return RmsdResponse(
        jobId=job_id,
        values=values,
        threshold=request.threshold,
        successRate=success_rate(values, threshold=request.threshold),
        structureMatch=structure_match,
    )


@router.post("/jobs/{job_id}/cluster", response_model=ClusterResponse)
def cluster_job_poses(job_id: str, request: ClusterRequest) -> ClusterResponse:
    """BUTINA-cluster this job's poses by symmetry-corrected heavy-atom RMSD.

    On-demand and report-only: the result is never written into the job
    (front-end caches it; persistence is TASK-07's call). Distances share
    ``rmsd.rmsd_between`` — the same no-superposition symmetry path as redocking RMSD.
    """
    from vinastudio.core.chem.cluster import cluster_poses
    from vinastudio.core.chem.rmsd import load_poses

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")
    if not state.poses_sdf:
        raise InvalidInputError("job has no pose SDF to cluster")

    try:
        clusters = cluster_poses(load_poses(state.poses_sdf), cutoff=request.cutoff)
    except (ValueError, RuntimeError) as exc:
        raise InvalidInputError(f"clustering failed: {exc}") from exc

    items = [
        ClusterItem(
            members=c.member_indices,
            centroid=c.centroid_index,
            size=c.size,
            meanRmsd=c.mean_rmsd,
        )
        for c in clusters
    ]
    return ClusterResponse(
        jobId=job_id,
        cutoff=request.cutoff,
        clusters=items,
        nClusters=len(items),
    )


# ── interaction fingerprints (TASK-16) ──────────────────────────────────────


@router.post("/jobs/{job_id}/ifp", response_model=IfpJobResponse)
def job_interaction_fingerprints(job_id: str, request: IfpJobRequest) -> IfpJobResponse:
    """Interaction fingerprints of this job's poses, BUTINA-clustered by similarity.

    Fingerprints (residue columns + bits) are cached in the job's
    ``analysis.json`` keyed by receptor identity + poses text; clustering is
    recomputed per request because the cutoff is a view parameter
    (task book勘误 ④).  The receptor comes from the job's own params — the
    caller never passes a path (勘误 ⑦).
    """
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")
    if not state.poses_sdf:
        # Design §3: a completed job with no pose SDF is "not ready", same
        # family as a non-completed job — 409, not a bad-request 422.
        raise HTTPException(status_code=409, detail="job has no pose SDF")

    receptor_path = (state.params or {}).get("receptor_path", "")
    if (
        not isinstance(receptor_path, str)
        or not receptor_path
        or not Path(receptor_path).is_file()
    ):
        raise InvalidInputError("job has no usable receptor path for fingerprints")

    try:
        payload, cached = _ifp_payload_cached(job_id, receptor_path, state.poses_sdf)
    except (ValueError, OSError, RuntimeError) as exc:
        raise InvalidInputError(f"fingerprint computation failed: {brief_error(exc)}") from exc

    residues = [IfpResidue(**row) for row in payload["residues"]]
    fingerprints = [IfpFingerprint(**row) for row in payload["fingerprints"]]

    bit_sets = [frozenset(tuple(pair) for pair in fp.pairs) for fp in fingerprints]
    distances = [
        [1.0 - tanimoto(a, b) for b in bit_sets] for a in bit_sets
    ]
    clusters = [
        IfpClusterRow(members=members, centroid=centroid, size=len(members))
        for members, centroid in butina_clustering(distances, request.cutoff)
    ]

    return IfpJobResponse(
        jobId=job_id,
        residues=residues,
        types=list(payload["types"]),
        fingerprints=fingerprints,
        clusters=clusters,
        nClusters=len(clusters),
        cutoff=request.cutoff,
        cached=cached,
    )


def _ifp_payload_cached(
    job_id: str, receptor_path: str, poses_sdf: str
) -> tuple[dict[str, Any], bool]:
    """Cached fingerprint payload, or a fresh compute written to the cache.

    A corrupt or missing ``analysis.json`` is a miss, never an error — the
    cache exists to save work, not to gate it (task book勘误 ④).
    """
    params_hash = _ifp_params_hash(receptor_path, poses_sdf)
    cached_payload = _read_ifp_cache(job_id, params_hash)
    if cached_payload is not None:
        return cached_payload, True

    receptor_atoms = parse_receptor_atoms(receptor_path)
    bit_sets = [
        fingerprint(receptor_atoms, parse_ligand_sdf(record))
        for record in _split_pose_records(poses_sdf)
    ]

    residues, index_of = residue_columns(receptor_atoms, bit_sets)
    fingerprints = []
    for index, bits in enumerate(bit_sets):
        pairs = sorted((index_of[key], order) for key, order in bits)
        fingerprints.append({"index": index, "pairs": pairs, "nContacts": len(pairs)})

    payload = {
        "residues": residues,
        "types": list(CONTACT_TYPES),
        "fingerprints": fingerprints,
    }
    try:
        _write_ifp_cache(job_id, params_hash, payload)
    except OSError as exc:
        # The compute already succeeded; a cache that cannot be written is a
        # slower next request, not a failed one.
        log.warning("ifp cache write failed for %s: %s", job_id, exc)
    return payload, False


def _ifp_params_hash(receptor_path: str, poses_sdf: str) -> str:
    """Identity of the (receptor file, poses text) pair a fingerprint depends on."""
    stat = Path(receptor_path).stat()
    poses_digest = hashlib.sha256(poses_sdf.encode("utf-8")).hexdigest()
    material = "｜".join(
        ["ifp-v1", receptor_path, str(stat.st_size), str(stat.st_mtime_ns), poses_digest]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_ifp_cache(job_id: str, params_hash: str) -> dict[str, Any] | None:
    """The kind="ifp" entry when its hash still matches; anything else is a miss."""
    path = job_dir(job_id) / ANALYSIS_CACHE_FILENAME
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if (
            isinstance(entry, dict)
            and entry.get("kind") == "ifp"
            and entry.get("paramsHash") == params_hash
            and isinstance(entry.get("payload"), dict)
        ):
            return entry["payload"]
    return None


def _write_ifp_cache(job_id: str, params_hash: str, payload: dict[str, Any]) -> None:
    """Replace the kind="ifp" entry in analysis.json (tmp file + os.replace)."""
    path = job_dir(job_id) / ANALYSIS_CACHE_FILENAME
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            entries = []
    except (OSError, json.JSONDecodeError):
        entries = []
    entries = [
        entry
        for entry in entries
        if not (isinstance(entry, dict) and entry.get("kind") == "ifp")
    ]
    entries.append({"kind": "ifp", "paramsHash": params_hash, "payload": payload})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _split_pose_records(poses_sdf: str) -> list[str]:
    """Split a multi-record SDF into per-pose records (``$$$$``-terminated)."""
    records: list[str] = []
    current: list[str] = []
    for line in poses_sdf.split("\n"):
        current.append(line)
        if line.startswith("$$$$"):
            records.append("\n".join(current))
            current = []
    if any(line.strip() for line in current):
        records.append("\n".join(current))
    return records


@router.get("/batch/{job_id}", response_model=BatchJobStatus)
def get_batch_status(job_id: str) -> BatchJobStatus:
    """Return the current state of a batch docking job."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")

    return BatchJobStatus(
        jobId=state.job_id,
        status=state.status,
        progress=state.progress,
        totalLigands=state.total_ligands,
        completedLigands=state.completed_ligands,
        failedLigands=state.failed_ligands,
        currentLigand=state.current_ligand,
        ligands=[
            BatchLigandProgress(
                ligandIndex=r.get("ligandIndex", 0),
                label=r.get("label", ""),
                status=r.get("status", ""),
                affinity=r.get("bestAffinity"),
                error=r.get("error", ""),
                qed=r.get("qed"),
                lipinskiViolations=r.get("lipinskiViolations"),
            )
            for r in state.batch_results
        ],
        error=state.error,
        elapsedMs=state.elapsed_ms,
    )


@router.get("/batch/{job_id}/progress", response_model=BatchJobStatus)
def get_batch_progress(job_id: str) -> BatchJobStatus:
    """Counters/current ligand only; the poll endpoint never ships every row."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    return BatchJobStatus(
        jobId=state.job_id,
        status=state.status,
        progress=state.progress,
        totalLigands=state.total_ligands,
        completedLigands=state.completed_ligands,
        failedLigands=state.failed_ligands,
        currentLigand=state.current_ligand,
        ligands=[],
        error=state.error,
        elapsedMs=state.elapsed_ms,
    )


@router.get("/batch/{job_id}/result", response_model=BatchJobResult)
def get_batch_result(job_id: str) -> BatchJobResult:
    """Return completed batch docking results."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    return BatchJobResult(
        jobId=state.job_id,
        status="completed",
        results=[
            BatchLigandResult(
                ligandIndex=r.get("ligandIndex", 0),
                label=r.get("label", ""),
                status=r.get("status", ""),
                pdbqt=r.get("pdbqt", ""),
                energies=[],
                bestAffinity=r.get("bestAffinity"),
                nPoses=r.get("nPoses", 0),
                elapsedMs=r.get("elapsedMs"),
                outDir=r.get("outDir", ""),
                error=r.get("error", ""),
                qed=r.get("qed"),
                lipinskiViolations=r.get("lipinskiViolations"),
            )
            for r in state.batch_results
        ],
        total=state.total_ligands,
        completed=state.completed_ligands,
        failed=state.failed_ligands,
        elapsedMs=state.elapsed_ms,
    )


@router.get("/batch/{job_id}/export-csv")
def export_batch_csv(job_id: str) -> dict[str, str]:
    """Export batch docking results as CSV text."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    # The artifact written at completion is the full ranking even when the
    # index only kept the top slice (restored sessions read it back, but a
    # missing CSV must still export whatever rows remain in memory).
    csv_text = ""
    try:
        csv_text = (job_dir(job_id) / BATCH_RESULTS_CSV_FILENAME).read_text(encoding="utf-8")
    except OSError:
        csv_text = ""
    if not csv_text:
        csv_text = _batch_csv_text(state.batch_results)
    return {"csv": csv_text, "filename": f"batch_{job_id}.csv"}


@router.post("/jobs/{job_id}/export-pose", response_model=ExportPoseResponse)
def export_pose(job_id: str, request: ExportPoseRequest) -> ExportPoseResponse:
    """Export a single pose from a completed docking job."""
    from vinastudio.core.chem.export import poses_to_sdf
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    doc = parse_pdbqt(state.poses_pdbqt)
    idx = request.poseIndex - 1
    if idx < 0 or idx >= doc.n_poses:
        raise InvalidInputError(
            f"pose {request.poseIndex} does not exist; the result has {doc.n_poses} poses"
        )

    pose = doc.poses[idx]

    # Extract single-pose PDBQT by rewriting MODEL/ENDMDL
    lines: list[str] = []
    lines.append(f"MODEL  {request.poseIndex}")
    if state.poses_pdbqt:
        in_model = False
        for raw_line in state.poses_pdbqt.splitlines():
            line = raw_line.rstrip()
            if line.startswith("MODEL"):
                current_model = int(line.split()[-1]) if len(line.split()) > 1 else 1
                in_model = current_model == request.poseIndex
                if in_model:
                    lines.append(line)
                continue
            if line.startswith("ENDMDL"):
                if in_model:
                    lines.append(line)
                    break
                continue
            if in_model and (line.startswith("ATOM") or line.startswith("HETATM")
                            or line.startswith("REMARK") or line.startswith("ROOT")
                            or line.startswith("ENDROOT") or line.startswith("BRANCH")
                            or line.startswith("ENDBRANCH") or line.startswith("TORSDOF")):
                lines.append(line)
    single_pdbqt = "\n".join(lines) + "\n" if lines else ""

    # Convert to SDF
    sdf = ""
    try:
        sdf_result = poses_to_sdf(single_pdbqt, title_prefix="pose")
        sdf = sdf_result.sdf
    except (ImportError, RuntimeError, ValueError) as exc:
        log.warning("SDF export failed for pose %d: %s", request.poseIndex, exc)

    return ExportPoseResponse(
        poseIndex=request.poseIndex,
        affinity=pose.energy or 0.0,
        pdbqt=single_pdbqt,
        sdf=sdf,
    )


def _interactive_map_cells(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    spacing: float,
    force_even_voxels: bool,
) -> int:
    """Vina grid cells for one interactive map set."""
    box = Box(center=center, size=size, spacing=spacing, force_even_voxels=force_even_voxels)
    return math.prod(box.voxels)


def _check_interactive_map_budget(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    spacing: float,
    force_even_voxels: bool,
) -> None:
    cells = _interactive_map_cells(center, size, spacing, force_even_voxels)
    if cells > _INTERACTIVE_MAX_CELLS:
        raise InvalidInputError(
            f"interactive box has {cells:,} grid cells (limit "
            f"{_INTERACTIVE_MAX_CELLS:,}); use a smaller box or run a docking job"
        )


def _configure_vina(
    request: ScoreRequest | OptimizeRequest | RandomizeRequest,
) -> Any:
    """Create and configure a Vina instance from a scoring/optimization request.

    These endpoints build their own affinity maps in this process, so they only
    accept scoring functions that can: ``ad4`` needs externally generated
    AutoGrid4 maps, which is the same limitation ``/start`` reports.
    """
    if request.scoring not in NATIVE_MAP_SCORING:
        raise InvalidInputError(
            f"{request.scoring} scoring needs existing AutoGrid4 maps and cannot "
            "be used for interactive scoring"
        )

    if request.ligandPath and not Path(request.ligandPath).exists():
        raise InvalidInputError(f"ligand file not found: {request.ligandPath}")

    _validate_box(
        request.receptorPath,
        request.center,
        request.size,
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
    )
    _check_interactive_map_budget(
        request.center, request.size, request.spacing, request.forceEvenVoxels
    )

    from vina import Vina  # type: ignore[import-untyped]

    # Interactive scoring/optimisation run at seed 0 unless the request carries
    # one (only randomise does: it is the stochastic call).
    v = Vina(
        sf_name=request.scoring,
        cpu=0,
        seed=getattr(request, "seed", 0),
        verbosity=0,
    )
    v.set_receptor(
        rigid_pdbqt_filename=request.receptorPath,
        flex_pdbqt_filename=request.flexReceptorPath or None,
    )
    if request.ligandPdbqtString:
        v.set_ligand_from_string(request.ligandPdbqtString)
    elif request.ligandPath:
        v.set_ligand_from_file(request.ligandPath)
    else:
        raise InvalidInputError("either ligandPath or ligandPdbqtString must be provided")

    if request.weights is not None:
        v.set_weights(request.weights)

    v.compute_vina_maps(
        center=list(request.center),
        box_size=list(request.size),
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
    )
    return v


def _reject_cli_weights(weights: list[float] | None) -> None:
    if weights is not None:
        raise InvalidInputError(
            "custom scoring weights are supported by the Python API backend only; "
            "the Vina CLI does not expose them"
        )


def _interactive_params(
    request: ScoreRequest | OptimizeRequest | RandomizeRequest,
) -> DockingParams:
    """The interactive request as the backend-neutral parameter object."""
    _validate_box(
        request.receptorPath,
        request.center,
        request.size,
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
    )
    return DockingParams(
        receptor_path=request.receptorPath,
        flex_pdbqt_path=request.flexReceptorPath,
        ligand_path=request.ligandPath,
        ligand_pdbqt_string=request.ligandPdbqtString,
        center=request.center,
        size=request.size,
        scoring=request.scoring,
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
        weights=request.weights,
        verbosity=0,
    )


def _exported_pose(v: Any, operation: str) -> str:
    """The conformation Vina is holding after ``operation``.

    ``write_pose`` (singular) is the writer for this: it documents itself as
    "write pose (after randomize or optimize)". The plural ``write_poses`` reads
    the *docking* pose store, which neither of those calls fills — using it here
    is what made these endpoints return an empty conformation for as long as they
    did. The guard stays because silence is worse than an error: a response must
    never claim to carry a conformation that was not written.
    """
    with tempfile.TemporaryDirectory(prefix="vinastudio-pose-") as scratch:
        path = Path(scratch) / "pose.pdbqt"
        v.write_pose(str(path), overwrite=True)
        if not path.is_file():
            raise EngineCapabilityError(
                f"this engine produced no conformation for {operation}. Fetch the "
                "command-line binary (`uv run python scripts/fetch_vina_cli.py`) and it "
                "will be used instead."
            )
        return path.read_text(encoding="utf-8", errors="replace")


@router.post("/score", response_model=ScoreResponse)
def score_pose(request: ScoreRequest) -> ScoreResponse:
    """Score the current ligand conformation without optimisation."""
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    if resolve_backend() == CLI_BACKEND:
        _reject_cli_weights(request.weights)
        with tempfile.TemporaryDirectory(prefix="vinastudio-score-") as scratch:
            return ScoreResponse(**score_cli(_interactive_params(request), scratch))

    with _INTERACTIVE_MAPS:
        v = _configure_vina(request)
        energies = v.score(unbound_energy=request.unboundEnergy)
    # score() returns [total, lig_inter, flex_inter, other_inter, flex_intra, lig_intra, torsions, lig_intra_best]
    return ScoreResponse(
        total=energies[0],
        inter=energies[1] + energies[2] + energies[3],
        intra=energies[4] + energies[5],
        torsions=energies[6],
        intra_best=energies[7],
    )


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_pose(request: OptimizeRequest) -> OptimizeResponse:
    """Locally optimise the ligand conformation."""
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    if resolve_backend() == CLI_BACKEND:
        _reject_cli_weights(request.weights)
        with tempfile.TemporaryDirectory(prefix="vinastudio-optimize-") as scratch:
            energy, pose = optimize_cli(_interactive_params(request), request.maxSteps, scratch)
        return OptimizeResponse(energy=energy, ligandPdbqt=pose)

    with _INTERACTIVE_MAPS:
        v = _configure_vina(request)
        # optimize() returns the same eight-value decomposition as score(); the
        # response reports the total, which is its first column. (It used to be
        # handed the whole array, which the response model rejected outright.)
        breakdown = v.optimize(max_steps=request.maxSteps)
        return OptimizeResponse(
            energy=float(breakdown[0]),
            ligandPdbqt=_exported_pose(v, "optimisation"),
        )


@router.post("/randomize", response_model=RandomizeResponse)
def randomize_pose(request: RandomizeRequest) -> RandomizeResponse:
    """Randomise the ligand conformation within the binding site.

    Vina keeps the lowest-energy of ``maxSteps`` random candidates, so the maps
    (receptor + box) are required. ``seed`` is passed through but **does not make
    the result reproducible**: Vina's randomisation seeds itself, on both the
    Python API and the binary (measured 2026-10-15 — two runs with the same seed
    differ). The field is kept because the request shape is shared with docking.
    """
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    if resolve_backend() == CLI_BACKEND:
        _reject_cli_weights(request.weights)
        with tempfile.TemporaryDirectory(prefix="vinastudio-randomize-") as scratch:
            pose = randomize_cli(_interactive_params(request), request.maxSteps, scratch)
        return RandomizeResponse(ligandPdbqt=pose)

    with _INTERACTIVE_MAPS:
        v = _configure_vina(request)
        v.randomize(max_steps=request.maxSteps)
        return RandomizeResponse(ligandPdbqt=_exported_pose(v, "randomisation"))


@router.get("/jobs/{job_id}/export-csv")
def export_csv(job_id: str, referencePath: str | None = None) -> dict[str, str]:
    """Export docking results as CSV text.

    With ``referencePath`` the export gains an ``rmsd_vs_ref`` column (empty
    when the reference is a different structure — warn, never reject).
    """
    import csv
    import io

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    rmsd_values: list[float] = []
    if referencePath is not None:
        from vinastudio.core.chem.rmsd import reference_matches_poses, rmsd_vs_reference

        ref_path = Path(referencePath)
        if not ref_path.exists():
            raise InvalidInputError(f"reference not found: {referencePath}")
        if reference_matches_poses(state.poses_sdf, ref_path) is not False:
            rmsd_values = rmsd_vs_reference(state.poses_sdf, ref_path)

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["pose", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"]
    if referencePath is not None:
        header.append("rmsd_vs_ref")
    writer.writerow(header)
    for position, pose in enumerate(state.poses):
        row = [
            pose.get("index", ""),
            pose.get("affinity", ""),
            pose.get("rmsdLower", ""),
            pose.get("rmsdUpper", ""),
        ]
        if referencePath is not None:
            row.append(rmsd_values[position] if position < len(rmsd_values) else "")
        writer.writerow(row)
    return {"csv": buf.getvalue(), "filename": f"docking_{job_id}.csv"}


def _svg_document(svg: str) -> str:
    """Standalone SVG file source: add the XML prologue when the DOM serializer omitted it."""
    if svg.lstrip().startswith("<?xml"):
        return svg
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg


def _result_bundles_dir() -> Path:
    """The dedicated, user-facing workspace directory for exported bundles.

    Keep this outside ``jobs/`` so people can find the files without knowing a
    job id.  With no active workspace (tests, first-run fallback) mirror the
    fallback layout beside ``workspace_root()``.
    """
    from vinastudio.core.workspace import exports_dir
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    root = (exports_dir(ws) if ws is not None else workspace_root().parent / "exports")
    target = root / "result-bundles"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _bundle_params(params: dict[str, Any]) -> dict[str, Any]:
    """Drop inline structure payloads; a bundle carries files, not megabyte strings."""
    return {key: value for key, value in params.items() if key not in _BUNDLE_INLINE_KEYS}


def _bundle_job_payload(state: JobState) -> dict[str, Any]:
    """Machine-readable result snapshot; paths and large strings do not travel."""
    return {
        "schemaVersion": 1,
        "jobId": state.job_id,
        "status": "completed",
        "scoring": state.scoring,
        "createdAt": state.created_at,
        "label": state.label,
        "params": _bundle_params(state.params),
        "poses": [dict(pose) for pose in state.poses],
        "bestAffinity": state.best_affinity,
        "nPoses": state.n_poses,
        "elapsedMs": state.elapsed_ms,
    }


def _bundle_manifest(state: JobState, members: list[str]) -> dict[str, Any]:
    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "appVersion": __version__,
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "jobId": state.job_id,
        "label": state.label,
        "members": sorted(members),
    }


def _bundle_csv(state: JobState) -> str:
    """Pose table for the bundle — the reference-free subset of export-csv."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["pose", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"])
    for pose in state.poses:
        writer.writerow(
            [
                pose.get("index", ""),
                pose.get("affinity", ""),
                pose.get("rmsdLower", ""),
                pose.get("rmsdUpper", ""),
            ]
        )
    return buf.getvalue()


def _bundle_config(state: JobState) -> str:
    """Human-readable parameter record shipped next to the results."""
    created = datetime.fromtimestamp(state.created_at).astimezone()
    lines = [
        f"job_id: {state.job_id}",
        f"label: {state.label or '-'}",
        f"status: {state.status}",
        f"scoring: {state.scoring}",
        f"created: {created.isoformat(timespec='seconds')}",
    ]
    if state.elapsed_ms is not None:
        lines.append(f"elapsed_ms: {state.elapsed_ms}")
    for key, value in sorted(state.params.items()):
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            rendered = ", ".join(str(item) for item in value)
        elif isinstance(value, bool):
            rendered = "yes" if value else "no"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines) + "\n"


@router.post("/jobs/{job_id}/export-bundle", response_model=Artifact)
def export_bundle(job_id: str, request: ExportBundleRequest) -> Artifact:
    """Pack a completed single-job run into one self-contained zip artifact.

    The bundle lands in ``jobs/<id>/export/`` with a fixed name: re-exporting
    overwrites instead of piling up copies in the artifact list, and the
    ``/artifacts`` URL stays valid across sessions (TASK-07 restores).
    """
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.is_batch:
        raise HTTPException(
            status_code=409,
            detail="batch jobs have no pose bundle; use export-csv for rows",
        )
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    include = set(request.include)
    svg = request.svg2d if "svg2d" in include else None
    if svg is not None and not svg_is_safe(svg):
        raise InvalidInputError("svg2d rejected: contains script-capable content")

    members: list[tuple[str, str]] = []
    if "sdf" in include:
        members.append(("poses.sdf", state.poses_sdf))
    if "csv" in include:
        members.append(("results.csv", _bundle_csv(state)))
    if "config" in include:
        members.append(("config.txt", _bundle_config(state)))
    if svg:
        members.append(
            ("interactions-2d.svg", _svg_document(svg)),
        )
    report_html = ""
    if "html" in include:
        report_html = render_report(
            lang=request.lang,
            job_id=state.job_id,
            label=state.label,
            status=state.status,
            created=datetime.fromtimestamp(state.created_at)
            .astimezone()
            .isoformat(timespec="seconds"),
            elapsed=f"{state.elapsed_ms / 1000:.1f} s" if state.elapsed_ms else None,
            scoring=state.scoring,
            params=state.params,
            poses=state.poses,
            svg=svg,
        )
        members.append(("report.html", report_html))
    if not members:
        raise InvalidInputError("nothing to export: the requested members produced no files")

    # Always ship the import metadata: a bundle without job.json/log can be
    # read as a report, but cannot be restored as a result.  The optional
    # members stay driven by the dialog.
    members.append(("job.json", json.dumps(_bundle_job_payload(state), ensure_ascii=False, indent=2)))
    members.append(("job.log", "\n".join(state.log) + ("\n" if state.log else "")))
    manifest = _bundle_manifest(state, [name for name, _ in members] + ["manifest.json"])
    members.insert(0, ("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)))

    export_root = _result_bundles_dir()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    label = slugify(state.label or "result", fallback="result", limit=40)
    base = f"{stamp}-{state.job_id}-{label}"
    zip_path = export_root / f"{base}.zip"
    counter = 1
    while zip_path.exists():
        zip_path = export_root / f"{base}-{counter}.zip"
        counter += 1
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in members:
            bundle.writestr(name, content)

    token = uuid.uuid4().hex
    _BUNDLE_DOWNLOADS[token] = zip_path
    while len(_BUNDLE_DOWNLOADS) > _BUNDLE_DOWNLOAD_LIMIT:
        _BUNDLE_DOWNLOADS.pop(next(iter(_BUNDLE_DOWNLOADS)))

    return Artifact(
        name=zip_path.name,
        path=str(zip_path),
        url=f"/api/docking/result-bundles/{token}",
        bytes=zip_path.stat().st_size,
        kind="zip",
    )


@router.get("/result-bundles/{token}")
def download_result_bundle(token: str) -> FileResponse:
    """Serve a bundle by its server-issued download token."""
    path = _BUNDLE_DOWNLOADS.get(token)
    if path is None or not path.is_file() or path.suffix.lower() != ".zip":
        raise HTTPException(status_code=404, detail="result bundle not found")
    return FileResponse(str(path), media_type="application/zip", filename=path.name)


def _read_result_bundle(payload: bytes) -> dict[str, bytes]:
    """Read a v1 bundle with no path traversal, symlinks or zip bombs."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
            infos = bundle.infolist()
            if len(infos) > BUNDLE_MAX_ENTRIES:
                raise InvalidInputError("result bundle has too many members")
            contents: dict[str, bytes] = {}
            total = 0
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                if (
                    not name
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or "\\" in name
                    or name.endswith("/")
                    or name in contents
                    or name not in BUNDLE_MEMBERS
                ):
                    raise InvalidInputError(f"result bundle member rejected: {name}")
                # A symlink entry is not a file this reader will follow.
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise InvalidInputError(f"result bundle symlink rejected: {name}")
                total += info.file_size
                if total > max_upload_bytes():
                    raise InvalidInputError("result bundle expands beyond the upload limit")
                contents[name] = bundle.read(name)
    except InvalidInputError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise InvalidInputError(f"not a readable result bundle: {exc}") from exc

    missing = BUNDLE_REQUIRED - contents.keys()
    if missing:
        raise InvalidInputError(
            "result bundle is missing: " + ", ".join(sorted(missing))
        )
    return contents


def _import_result_bundle(payload: bytes) -> ImportBundleResponse:
    contents = _read_result_bundle(payload)

    try:
        manifest = json.loads(contents["manifest.json"].decode("utf-8"))
        job = json.loads(contents["job.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidInputError("result bundle metadata is not valid JSON") from exc
    if not isinstance(manifest, dict) or not isinstance(job, dict):
        raise InvalidInputError("result bundle metadata is not an object")
    if manifest.get("format") != BUNDLE_FORMAT or manifest.get("version") != BUNDLE_VERSION:
        raise InvalidInputError("unsupported result bundle format")

    if job.get("status") != "completed":
        raise InvalidInputError("result bundle is not a completed run")
    if job.get("isBatch") or job.get("isScreening") or job.get("isSiteScreening"):
        raise InvalidInputError("only single docking results can be imported")

    params = job.get("params")
    if not isinstance(params, dict):
        raise InvalidInputError("result bundle has no parameter record")
    scoring = job.get("scoring")
    if scoring not in SCORING_WEIGHT_COUNT:
        raise InvalidInputError(f"unsupported scoring function: {scoring}")

    raw_poses = job.get("poses")
    if not isinstance(raw_poses, list) or not raw_poses:
        raise InvalidInputError("result bundle has no poses")
    try:
        poses = [PoseInfo.model_validate(pose).model_dump() for pose in raw_poses]
    except ValueError as exc:
        raise InvalidInputError("result bundle poses are malformed") from exc

    try:
        created_at = float(job.get("createdAt") or time.time())
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("result bundle has an invalid creation time") from exc
    elapsed = job.get("elapsedMs")
    try:
        elapsed_ms = int(elapsed) if elapsed is not None else None
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("result bundle has an invalid elapsed time") from exc
    best = job.get("bestAffinity")
    try:
        best_affinity = (
            float(best)
            if best is not None
            else min(float(pose["affinity"]) for pose in poses)
        )
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("result bundle has an invalid best affinity") from exc

    try:
        poses_sdf = contents["poses.sdf"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidInputError("poses.sdf is not UTF-8") from exc
    log_text = contents.get("job.log", b"").decode("utf-8", errors="replace")

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target: Path | None = None
    for _ in range(3):
        candidate = job_dir(f"import-{stamp}-{uuid.uuid4().hex[:6]}")
        if not candidate.exists():
            target = candidate
            break
    if target is None:
        raise InvalidInputError("could not allocate a directory for the imported result")

    label = str(job.get("label") or "").strip()
    label = f"{label} (imported)" if label else "Imported result"
    target.mkdir(parents=True)
    try:
        (target / POSES_SDF_FILENAME).write_text(poses_sdf, encoding="utf-8")
        if log_text:
            (target / JOB_LOG_FILENAME).write_text(log_text, encoding="utf-8")
        for name in BUNDLE_OPTIONAL:
            if name in contents and name != "job.log":
                (target / name).write_bytes(contents[name])
        state = JobState(
            job_id=target.name,
            status="completed",
            progress=100,
            log=log_text.splitlines(),
            scoring=scoring,
            created_at=created_at,
            elapsed_ms=elapsed_ms,
            label=label,
            params=params,
            poses=poses,
            best_affinity=best_affinity,
            n_poses=len(poses),
            poses_sdf=poses_sdf,
        )
        job_manager.register_imported(state)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return ImportBundleResponse(jobId=state.job_id, label=state.label)


@router.post("/import-bundle", response_model=ImportBundleResponse)
async def import_bundle(
    x_requested_with: Annotated[str, Header()],
    file: UploadFile = File(...),
) -> ImportBundleResponse:
    """Restore a result bundle as a new, read-only completed job.

    The zip bytes arrive as multipart, not as a user-supplied path: the same
    non-simple-request header as ``/api/files/upload`` applies, and no path
    from the request ever reaches the filesystem.  The imported run gets a
    fresh id, so the current project and its results stay untouched.
    """
    name = Path(file.filename or "bundle.zip").name
    if Path(name).suffix.lower() != ".zip":
        raise InvalidInputError("result bundle must be a .zip file")
    limit = max_upload_bytes()
    if file.size is not None and file.size > limit:
        raise InvalidInputError("result bundle exceeds the upload limit")
    payload = await file.read()
    if not payload:
        raise InvalidInputError("result bundle is empty")
    if len(payload) > limit:
        raise InvalidInputError("result bundle exceeds the upload limit")
    return _import_result_bundle(payload)
