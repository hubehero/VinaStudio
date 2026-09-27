"""Docking endpoints: start, status, cancel, list jobs."""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from vinastudio.config import NATIVE_MAP_SCORING
from vinastudio.core.errors import InvalidInputError, JobNotFoundError
from vinastudio.core.paths import BATCH_RESULTS_CSV_FILENAME, job_dir, workspace_root
from vinastudio.core.report import render_report, svg_is_safe
from vinastudio.schemas.docking import (
    BatchDockingRequest,
    BatchJobCreated,
    BatchJobResult,
    BatchJobStatus,
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
    ExportBundleRequest,
    ExportPoseRequest,
    ExportPoseResponse,
    OptimizeRequest,
    OptimizeResponse,
    PoseFindingModel,
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
from vinastudio.server.routers.artifacts import ARTIFACT_URL_PREFIX

log = logging.getLogger(__name__)
router = APIRouter(prefix="/docking", tags=["docking"])


@router.get("/defaults", response_model=DockingDefaultsResponse)
def get_defaults() -> DockingDefaultsResponse:
    """Return default docking parameters for the UI form."""
    return DockingDefaultsResponse()


@router.get("/info", response_model=VinaInfoResponse)
def get_info() -> VinaInfoResponse:
    """Return Vina library version and capabilities."""
    import multiprocessing

    from vinastudio.config import SCORING_WEIGHT_COUNT

    return VinaInfoResponse(
        version="autoDockVina",
        supportedScoringFunctions=list(SCORING_WEIGHT_COUNT.keys()),
        cpuCount=multiprocessing.cpu_count(),
        maxCPUs=1024,
    )


@router.get("/cite", response_model=CitationResponse)
def get_citation(scoring: str = "vina") -> CitationResponse:
    """Return citation text for the selected scoring function."""
    from vinastudio.config import SCORING_WEIGHT_COUNT

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
    }

    job_id = job_manager.start_job(params)
    return DockingJobCreated(jobId=job_id, status="queued")


@router.post("/batch", response_model=BatchJobCreated)
def batch_docking(request: BatchDockingRequest) -> BatchJobCreated:
    """Start a batch docking job in a spawned child process."""
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")
    if not request.ligands:
        raise InvalidInputError("ligands list is empty")

    params = {
        "receptor_path": request.receptorPath,
        "flex_pdbqt_path": request.flexReceptorPath,
        "center": list(request.center),
        "size": list(request.size),
        "ligands": [
            {"ligandPath": lig.ligandPath, "ligandPdbqtString": lig.ligandPdbqtString, "label": lig.label}
            for lig in request.ligands
        ],
        "scoring": request.scoring,
        "exhaustiveness": request.exhaustiveness,
        "n_poses": request.nPoses,
        "energy_range": request.energyRange,
        "min_rmsd": request.minRmsd,
        "cpu": request.cpu,
        "seed": request.seed,
        "no_refine": request.noRefine,
        "engine": request.engine,
    }

    job_id = job_manager.start_batch_job(params)
    return BatchJobCreated(jobId=job_id, status="queued", total=len(request.ligands))


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

    Symmetry-corrected (``GetBestRMS``); report-only. A reference that is a
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
    ``rmsd.rmsd_between`` — the same GetBestRMS path as redocking RMSD.
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
            )
            for r in state.batch_results
        ],
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

    v.compute_vina_maps(
        center=list(request.center),
        box_size=list(request.size),
        spacing=request.spacing,
        force_even_voxels=request.forceEvenVoxels,
    )
    return v


@router.post("/score", response_model=ScoreResponse)
def score_pose(request: ScoreRequest) -> ScoreResponse:
    """Score the current ligand conformation without optimisation."""
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

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

    v = _configure_vina(request)
    energy = v.optimize(max_steps=request.maxSteps)
    pdbqt = v.poses(n_poses=1, coordinates_only=False)
    return OptimizeResponse(energy=energy, ligandPdbqt=pdbqt)


@router.post("/randomize", response_model=RandomizeResponse)
def randomize_pose(request: RandomizeRequest) -> RandomizeResponse:
    """Randomise the ligand conformation within the binding site.

    Vina keeps the lowest-energy of ``maxSteps`` random candidates, so the
    maps (receptor + box) are required and ``seed`` makes the result
    reproducible.
    """
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    v = _configure_vina(request)
    v.randomize(max_steps=request.maxSteps)
    pdbqt = v.poses(n_poses=1, coordinates_only=False)
    return RandomizeResponse(ligandPdbqt=pdbqt)


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

    export_dir = job_dir(job_id) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / "result-bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in members:
            bundle.writestr(name, content)

    relative = zip_path.relative_to(workspace_root()).as_posix()
    return Artifact(
        name=zip_path.name,
        path=str(zip_path),
        url=f"{ARTIFACT_URL_PREFIX}/{relative}",
        bytes=zip_path.stat().st_size,
        kind="zip",
    )
