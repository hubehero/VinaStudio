"""Docking endpoints: start, status, cancel, list jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from vinastudio.config import NATIVE_MAP_SCORING
from vinastudio.core.errors import InvalidInputError, JobNotFoundError
from vinastudio.schemas.docking import (
    BatchDockingRequest,
    BatchJobCreated,
    BatchJobResult,
    BatchJobStatus,
    BatchLigandProgress,
    BatchLigandResult,
    CitationResponse,
    DockingDefaultsResponse,
    DockingJobCreated,
    DockingJobResult,
    DockingJobStatus,
    DockingJobSummary,
    DockingRequest,
    ExportPoseRequest,
    ExportPoseResponse,
    OptimizeRequest,
    OptimizeResponse,
    RandomizeRequest,
    RandomizeResponse,
    ScoreRequest,
    ScoreResponse,
    VinaInfoResponse,
)
from vinastudio.server.job_manager import manager as job_manager

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
    }

    job_id = job_manager.start_batch_job(params)
    return BatchJobCreated(jobId=job_id, status="queued", total=len(request.ligands))


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
            elapsed_ms=j.elapsed_ms,
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


def _batch_csv_text(batch_results: list[dict[str, Any]]) -> str:
    """Render batch rows as CSV text for download.

    ``pose_count`` reads ``nPoses``: the rows have never carried an
    ``energies`` list, so counting that always wrote 0.
    """
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ligand_index", "label", "status", "best_affinity_kcal_mol",
        "pose_count", "error",
    ])
    for r in batch_results:
        writer.writerow([
            r.get("ligandIndex", ""),
            r.get("label", ""),
            r.get("status", ""),
            r.get("bestAffinity", ""),
            r.get("nPoses", 0),
            r.get("error", ""),
        ])
    return buf.getvalue()


@router.get("/batch/{job_id}/export-csv")
def export_batch_csv(job_id: str) -> dict[str, str]:
    """Export batch docking results as CSV text."""
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    return {"csv": _batch_csv_text(state.batch_results), "filename": f"batch_{job_id}.csv"}


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
def export_csv(job_id: str) -> dict[str, str]:
    """Export docking results as CSV text."""
    import csv
    import io

    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if state.status != "completed":
        raise HTTPException(status_code=409, detail=f"job is {state.status}, not completed")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["pose", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"])
    for pose in state.poses:
        writer.writerow([
            pose.get("index", ""),
            pose.get("affinity", ""),
            pose.get("rmsdLower", ""),
            pose.get("rmsdUpper", ""),
        ])
    return {"csv": buf.getvalue(), "filename": f"docking_{job_id}.csv"}
