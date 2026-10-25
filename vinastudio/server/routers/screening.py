"""Virtual screening endpoints: libraries, runs, ranking (TASK-13).

Response shapes follow ``exchange/design/TASK-13-vscreen-workbench.md`` §3.
The per-molecule rows come from ``screening.jsonl`` (append-only, §4.2);
nothing here ever ships them on a status poll — ranking/export are the only
readers (千级轮询不回 5000 行).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from vinastudio.config import max_upload_bytes
from vinastudio.core.chem.library import (
    LibraryExistsError,
    import_library,
    is_valid_name,
    library_dir,
    library_exists,
    list_libraries,
    load_detail,
)
from vinastudio.core.errors import InvalidInputError, JobNotFoundError
from vinastudio.schemas.screening import (
    ImportedFailure,
    LibraryDetail,
    LibraryImportResult,
    LibrarySummary,
    RankingResponse,
    RankingRow,
    RankingSortBy,
    ScreeningRunCreated,
    ScreeningRunStatus,
    ScreeningRunSummary,
    ScreeningStartRequest,
)
from vinastudio.server.job_manager import (
    JobState,
    read_screening_rows,
    screening_jsonl_progress,
)
from vinastudio.server.job_manager import manager as job_manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/screening", tags=["screening"])

#: Exported rows are capped server-side; the default view is top-100 (§4.3).
_RANKING_TOP_MAX = 5000
_RANKING_TOP_DEFAULT = 100


def _require_run(job_id: str) -> JobState:
    state = job_manager.get_job(job_id)
    if state is None:
        raise JobNotFoundError(f"job {job_id} not found")
    if not state.is_screening:
        # A real id that is not a screening run is simply absent here.
        raise JobNotFoundError(f"screening run {job_id} not found")
    return state


def _run_summary(state: JobState) -> ScreeningRunSummary:
    return ScreeningRunSummary(
        jobId=state.job_id,
        library=str(state.params.get("library") or state.label),
        libraryDisplayName=(
            str(state.params.get("library_display_name"))
            if state.params.get("library_display_name")
            else None
        ),
        createdAt=state.created_at,
        status=state.status,
        progress=state.progress,
        totalLigands=state.total_ligands,
        completedLigands=state.completed_ligands,
        failedLigands=state.failed_ligands,
        bestAffinity=state.screening_best,
        error=state.error,
    )


def _run_status(state: JobState) -> ScreeningRunStatus:
    summary = _run_summary(state)
    return ScreeningRunStatus(
        **summary.model_dump(),
        currentLigand=state.current_ligand or None,
        elapsedMs=state.elapsed_ms,
    )


def _ranked_rows(
    job_id: str, sort_by: RankingSortBy, top: int
) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    """``( [(rank, row)], total )`` for completed rows — shared by the table
    and its CSV export so the two can never disagree (§4.3 parity).

    Sort: affinity asc (most negative first), qed desc, lipinski asc; nulls
    always sort last regardless of direction (a None cannot be compared to a
    number), ties break by ``ligandIndex`` asc. ``top`` is clamped 1..5000.
    """
    rows = [
        row for row in read_screening_rows(job_id)
        if row.get("status") == "completed"
    ]
    reverse = sort_by == "qed"

    def sort_key(row: dict[str, Any]) -> tuple[bool, float, int]:
        value = row.get(sort_by)
        missing = not isinstance(value, (int, float))
        numeric = 0.0 if missing else float(value)
        index = row.get("i")
        ligand_index = index if isinstance(index, int) else 0
        return (missing, -numeric if reverse else numeric, ligand_index)

    rows.sort(key=sort_key)
    total = len(rows)
    capped = max(1, min(int(top), _RANKING_TOP_MAX))
    ranked = [(position + 1, row) for position, row in enumerate(rows[:capped])]
    return ranked, total


def _ranking_row(rank: int, row: dict[str, Any]) -> RankingRow:
    return RankingRow(
        rank=rank,
        ligandIndex=int(row.get("i") or 0),
        name=str(row.get("name") or ""),
        affinity=row.get("affinity"),
        nPoses=row.get("nPoses"),
        qed=row.get("qed"),
        lipinskiViolations=row.get("lipinski"),
        elapsedMs=row.get("elapsedMs"),
        smiles=row.get("smiles"),
        outDir=row.get("outDir"),
    )


# --- libraries -------------------------------------------------------------


@router.get("/libraries", response_model=list[LibrarySummary])
def list_screening_libraries() -> list[LibrarySummary]:
    return [LibrarySummary(**row) for row in list_libraries()]


@router.post("/libraries/import", response_model=LibraryImportResult)
async def import_screening_library(
    name: str = Form(...),
    paths: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> LibraryImportResult:
    """Import a local SDF into a new library — dual origin (design §3).

    ``paths`` carries a JSON array of filesystem paths (native dialog);
    ``files`` the uploaded bytes (browser). At least one is required; both
    may be present and are imported together.
    """
    if not is_valid_name(name):
        raise HTTPException(status_code=400, detail=f"illegal library name: {name}")
    sources: list[Path] = []
    if paths:
        try:
            parsed = json.loads(paths)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="paths must be a JSON array of file paths"
            ) from None
        if not isinstance(parsed, list) or not all(isinstance(p, str) for p in parsed):
            raise HTTPException(
                status_code=400, detail="paths must be a JSON array of file paths"
            )
        for raw in parsed:
            source = Path(raw)
            if not source.is_file():
                raise HTTPException(
                    status_code=400, detail=f"source file not found: {raw}"
                )
            sources.append(source)
    uploads = list(files or [])
    if not sources and not uploads:
        raise HTTPException(
            status_code=400, detail="give at least one of paths or files"
        )
    if library_exists(name):
        raise HTTPException(
            status_code=409, detail=f"library already exists: {name}"
        )

    max_bytes = max_upload_bytes()
    with tempfile.TemporaryDirectory(prefix="vina-lib-import-") as tmp:
        for position, upload in enumerate(uploads):
            # Same double check as routers/files.py: the declared size before
            # reading, the real byte count after — a lying header cannot slip
            # a payload past the cap.
            declared = upload.size
            if declared is not None and declared > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"file too large: {declared} bytes exceeds the upload limit",
                )
            payload = await upload.read()
            if len(payload) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"file too large: {len(payload)} bytes exceeds the upload limit",
                )
            if not payload:
                raise HTTPException(
                    status_code=400,
                    detail=f"the uploaded file is empty: {upload.filename or ''}",
                )
            filename = Path(upload.filename or f"source-{position}.sdf").name
            target = Path(tmp) / f"{position:03d}-{filename}"
            target.write_bytes(payload)
            sources.append(target)

        try:
            report = import_library(name, sources)
        except LibraryExistsError:
            # Lost a race with a concurrent import after the pre-check.
            raise HTTPException(
                status_code=409, detail=f"library already exists: {name}"
            ) from None

    return LibraryImportResult(
        name=report.name,
        imported=report.imported,
        skipped=report.skipped,
        failedCount=report.failed_count,
        failed=[
            ImportedFailure(index=f.index, name=f.name, reason=f.reason)
            for f in report.failed
        ],
    )


@router.get("/libraries/{name}", response_model=LibraryDetail)
def get_screening_library(name: str) -> LibraryDetail:
    detail = load_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"library not found: {name}")
    return LibraryDetail(**detail)


# --- runs ------------------------------------------------------------------


@router.post("/runs", response_model=ScreeningRunCreated)
def start_run(request: ScreeningStartRequest) -> ScreeningRunCreated:
    """Start a screening run over a legacy or catalog library (§4.2)."""
    library_name = request.library
    if request.libraryId:
        from vinastudio.core.catalog import db as catalog_db
        from vinastudio.core.catalog.library import materialize_library
        from vinastudio.server.routers.workspace import get_active_workspace

        workspace = get_active_workspace()
        if workspace is None:
            raise InvalidInputError("no workspace configured")
        with catalog_db.transaction(catalog_db.catalog_path()) as conn:
            materialize_library(conn, request.libraryId, workspace=workspace)
        library_name = request.libraryId
    if library_name is None:
        raise HTTPException(status_code=422, detail="library or libraryId is required")
    detail = load_detail(library_name)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"library not found: {library_name}"
        )
    if not detail["entries"]:
        raise HTTPException(
            status_code=409, detail=f"library {library_name} has no entries"
        )
    receptor = Path(request.receptorPath)
    if not receptor.exists():
        raise InvalidInputError(f"receptor file not found: {request.receptorPath}")

    params: dict[str, Any] = {
        "library": library_name,
        "library_display_name": detail.get("displayName") or library_name,
        "library_dir": str(library_dir(library_name)),
        "entries": [
            {"index": int(entry["index"]), "name": str(entry["name"])}
            for entry in detail["entries"]
        ],
        "receptor_path": request.receptorPath,
        "flex_pdbqt_path": request.flexReceptorPath,
        "center": list(request.center),
        "size": list(request.size),
        "scoring": request.scoring,
        "exhaustiveness": request.exhaustiveness,
        "n_poses": request.nPoses,
        "energy_range": request.energyRange,
        "cpu": request.cpu,
        "seed": request.seed,
        "no_refine": request.noRefine,
        "engine": request.engine,
    }
    if request.parallelism is not None:
        params["parallelism"] = request.parallelism

    job_id = job_manager.start_screening_job(params)
    return ScreeningRunCreated(jobId=job_id)


@router.get("/runs", response_model=list[ScreeningRunSummary])
def list_runs() -> list[ScreeningRunSummary]:
    runs = [state for state in job_manager.list_jobs() if state.is_screening]
    return [
        _run_summary(state)
        for state in sorted(runs, key=lambda state: state.created_at, reverse=True)
    ]


@router.get("/runs/{job_id}", response_model=ScreeningRunStatus)
def get_run(job_id: str) -> ScreeningRunStatus:
    """Status of one run — counters and current ligand only, never the rows."""
    return _run_status(_require_run(job_id))


@router.post("/runs/{job_id}/cancel", status_code=204)
def cancel_run(job_id: str) -> Response:
    state = _require_run(job_id)
    if state.status != "running":
        raise HTTPException(status_code=409, detail=f"run is {state.status}, not running")
    if not job_manager.cancel_job(job_id):
        # Raced a settle between the check and the kill.
        raise HTTPException(status_code=409, detail="run is no longer running")
    return Response(status_code=204)


@router.post("/runs/{job_id}/resume", response_model=ScreeningRunStatus)
def resume_run(job_id: str) -> ScreeningRunStatus:
    """Relaunch the molecules with no terminal row yet (§4.2 断点续跑)."""
    state = _require_run(job_id)
    if state.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=409, detail=f"run is {state.status}, not failed or cancelled"
        )
    skip, _, _, _ = screening_jsonl_progress(job_id)
    if not skip:
        # §4.2: no terminal rows means there is no resume truth to build on
        # (a fresh crash with an unwritten jsonl must not silently re-run).
        raise HTTPException(
            status_code=409, detail="screening.jsonl has no terminal rows to resume"
        )
    roster = state.params.get("entries") or []
    remaining = [
        entry for entry in roster
        if isinstance(entry, dict) and int(entry.get("index", -1)) not in skip
    ]
    if not remaining:
        raise HTTPException(
            status_code=409, detail="no unfinished molecules to resume"
        )
    resumed = job_manager.resume_screening_job(job_id, skip)
    if resumed is None:
        raise JobNotFoundError(f"job {job_id} not found")
    return _run_status(resumed)


# --- ranking ---------------------------------------------------------------


@router.get("/runs/{job_id}/ranking", response_model=RankingResponse)
def get_ranking(
    job_id: str,
    sortBy: RankingSortBy = "affinity",
    top: int = _RANKING_TOP_DEFAULT,
) -> RankingResponse:
    """Completed rows sorted server-side; ``total`` counts before the cut."""
    _require_run(job_id)
    ranked, total = _ranked_rows(job_id, sortBy, top)
    return RankingResponse(
        total=total, rows=[_ranking_row(rank, row) for rank, row in ranked]
    )


@router.get("/runs/{job_id}/ranking/export")
def export_ranking(
    job_id: str,
    sortBy: RankingSortBy = "affinity",
    top: int = _RANKING_TOP_DEFAULT,
) -> dict[str, str]:
    """CSV of exactly the rows ``GET .../ranking`` would return (§4.3)."""
    _require_run(job_id)
    ranked, _total = _ranked_rows(job_id, sortBy, top)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "rank", "ligand_index", "label", "best_affinity_kcal_mol",
        "pose_count", "qed", "lipinski_violations",
    ])
    for rank, row in ranked:
        # csv renders None as an empty cell — the agreed null rule (§4.6).
        writer.writerow([
            rank,
            row.get("i"),
            row.get("name") or "",
            row.get("affinity"),
            row.get("nPoses"),
            row.get("qed"),
            row.get("lipinski"),
        ])
    return {"csv": buf.getvalue(), "filename": f"screening_{job_id}_ranking.csv"}
