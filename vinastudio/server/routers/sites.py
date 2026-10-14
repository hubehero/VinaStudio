"""Site-screen endpoints: rank candidate boxes by docking one ligand (S2).

``POST /api/sites/start`` runs a low-exhaustiveness docking of one ligand in
each candidate box and answers with the ranking. The affinities it produces
order the boxes; they are **not** production numbers (see the schema docstring).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from vinastudio.core.errors import InvalidInputError, JobNotFoundError
from vinastudio.schemas.sites import (
    SiteRow,
    SiteScreeningCreated,
    SiteScreeningRequest,
    SiteScreeningResult,
    SiteScreeningStatus,
)
from vinastudio.server.job_manager import JobState, read_site_rows
from vinastudio.server.job_manager import manager as job_manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sites", tags=["sites"])


def _ranked_rows(state: JobState) -> list[SiteRow]:
    """Rows joined with the boxes they ran in, ranked by best affinity.

    Scored boxes come first (most negative affinity first); boxes that failed or
    produced no pose keep their place at the end — they *were* tried, and hiding
    them would misrepresent the screen. Ties keep the order the caller sent, so
    two reads of the same run give the same table.
    """
    candidates = {
        int(candidate.get("index", position)): candidate
        for position, candidate in enumerate(state.params.get("candidates", []))
    }
    rows: list[SiteRow] = []
    for raw in read_site_rows(state.job_id):
        candidate = candidates.get(int(raw.get("i") or 0)) or {}
        center = candidate.get("center")
        size = candidate.get("size")
        rows.append(
            SiteRow(
                index=int(raw.get("i") or 0),
                label=str(raw.get("label") or ""),
                status=str(raw.get("status") or "failed"),  # type: ignore[arg-type]
                center=tuple(center) if center else None,  # type: ignore[arg-type]
                size=tuple(size) if size else None,  # type: ignore[arg-type]
                bestAffinity=raw.get("affinity"),
                nPoses=raw.get("nPoses"),
                elapsedMs=raw.get("elapsedMs"),
                error=raw.get("error"),
            )
        )

    scored = [row for row in rows if row.bestAffinity is not None]
    unscored = [row for row in rows if row.bestAffinity is None]
    scored.sort(key=lambda row: row.bestAffinity)  # type: ignore[arg-type,return-value]
    for rank, row in enumerate(scored, start=1):
        row.rank = rank
    return scored + unscored


def _require_job(job_id: str) -> JobState:
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    return state


@router.post("/start", response_model=SiteScreeningCreated)
def start_site_screen(request: SiteScreeningRequest) -> SiteScreeningCreated:
    """Dock one ligand into each candidate box and rank the boxes."""
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    if not request.ligandPath and not request.ligandPdbqtString:
        raise InvalidInputError("either ligandPath or ligandPdbqtString must be provided")
    if request.ligandPath and not Path(request.ligandPath).exists():
        raise InvalidInputError(f"ligand file not found: {request.ligandPath}")

    if request.flexReceptorPath and not Path(request.flexReceptorPath).exists():
        raise InvalidInputError(
            f"flex receptor file not found: {request.flexReceptorPath}"
        )

    if request.scoring == "ad4" and not request.mapPaths:
        raise InvalidInputError("ad4 scoring requires mapPaths")

    job_id = job_manager.start_site_screening_job({
        "receptor_path": request.receptorPath,
        "flex_pdbqt_path": request.flexReceptorPath,
        "ligand_path": request.ligandPath,
        "ligand_pdbqt_string": request.ligandPdbqtString,
        "candidates": [candidate.model_dump() for candidate in request.candidates],
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
    })
    return SiteScreeningCreated(jobId=job_id, status="running")


@router.get("/{job_id}", response_model=SiteScreeningStatus)
def get_site_screen(job_id: str) -> SiteScreeningStatus:
    """Status plus the rows that have landed so far."""
    state = _require_job(job_id)
    rows = _ranked_rows(state) if state.is_site_screening else []
    # Counted from the rows, not from the state's counters: the jsonl is the
    # append-only truth, while ``job.json`` only sees the last stage event — so
    # after a restart the two would disagree by exactly the rows in flight.
    completed = sum(1 for row in rows if row.status == "completed")
    return SiteScreeningStatus(
        jobId=state.job_id,
        status=state.status,
        progress=state.progress,
        stage=state.stage,
        error=state.error,
        elapsedMs=state.elapsed_ms,
        totalCandidates=state.total_ligands,
        completedCandidates=completed,
        failedCandidates=len(rows) - completed,
        currentLabel=state.current_ligand,
        rows=rows,
    )


@router.get("/{job_id}/result", response_model=SiteScreeningResult)
def get_site_screen_result(job_id: str) -> SiteScreeningResult:
    """The finished ranking. 409 while the screen is still running."""
    state = _require_job(job_id)
    if state.status != "completed":
        raise HTTPException(
            status_code=409, detail=f"job is {state.status}, not completed"
        )

    rows = _ranked_rows(state)
    best = next((row for row in rows if row.bestAffinity is not None), None)
    return SiteScreeningResult(
        jobId=state.job_id,
        status="completed",
        scoring=state.scoring,
        exhaustiveness=int(state.params.get("exhaustiveness") or 0),
        rows=rows,
        bestAffinity=best.bestAffinity if best else None,
        bestIndex=best.index if best else None,
        elapsedMs=state.elapsed_ms,
    )


@router.post("/{job_id}/cancel")
def cancel_site_screen(job_id: str) -> dict[str, str]:
    """Cancel a running screen by killing its worker process."""
    if not job_manager.cancel_job(job_id):
        raise JobNotFoundError(f"job {job_id} not found or not running")
    return {"status": "cancelled", "jobId": job_id}
