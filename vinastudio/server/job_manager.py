"""In-memory job manager for docking runs.

Each job owns a spawned child process, a reader thread that bridges pipe events
onto the asyncio loop, and an artifact directory under the workspace's
``jobs/`` folder (the same root ``/artifacts`` serves).  Cancellation kills the
child process.

The module-level ``manager`` singleton is the single entry point.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import multiprocessing
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Literal

from vinastudio.core.paths import (
    BATCH_RESULTS_CSV_FILENAME,
    JOB_LOG_FILENAME,
    JOB_STATE_FILENAME,
    POSES_SDF_FILENAME,
    job_log_path,
    job_state_path,
    workspace_root,
)

log = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]

#: Workers must start with ``spawn``.  A forked child inherits uvicorn's
#: *handled* signals — including SIGTERM, which makes ``terminate()`` a silent
#: no-op — and every live thread of the Qt + asyncio parent (deadlock risk).
#: ``spawn`` is the only start method where killing a worker actually works.
_MP = multiprocessing.get_context("spawn")

#: Extensions mapped onto ``ArtifactKind``; anything else is plain text.
_ARTIFACT_KINDS = {
    ".pdbqt": "pdbqt",
    ".pdb": "pdb",
    ".sdf": "sdf",
    ".json": "json",
    ".log": "log",
    ".zip": "zip",
}

#: Serialises join/kill on worker processes.  ``cancel_job`` (request thread)
#: and ``_reap`` (reader thread) drive the same child; concurrent ``join``s
#: race ``waitpid`` and can make ``is_alive()`` lie — which would send SIGTERM
#: to a pid that may already have been reused.
_PROC_OPS = threading.Lock()

#: Rows of a batch ranking kept inside ``job.json``.  Above this the full set
#: goes to a CSV artifact and the index stores the affinity-ranked top slice —
#: a library screen must never turn into a 50 MB JSON file (TASK-07 §8).
_BATCH_JSON_LIMIT = 100

#: Inline structure payloads are exactly the "large fields" the index must not
#: carry; the path on disk identifies the same molecule.
_INLINE_PDBQT_KEYS = frozenset({"ligandPdbqtString", "receptorPdbqtString", "pdbqtString"})

#: Persist the index when one of these event kinds mutates the state.
_PERSIST_EVENT_KINDS = frozenset({"stage", "completed", "failed"})


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress: int = 0
    stage: str | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: int | None = None
    scoring: str = "vina"
    created_at: float = field(default_factory=time.time)
    # Result data (populated on completion)
    poses: list[dict[str, Any]] = field(default_factory=list)
    best_affinity: float = 0.0
    n_poses: int = 0
    poses_pdbqt: str = ""
    poses_sdf: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # Batch-specific fields
    is_batch: bool = False
    total_ligands: int = 0
    completed_ligands: int = 0
    failed_ligands: int = 0
    current_ligand: str = ""
    batch_results: list[dict[str, Any]] = field(default_factory=list)
    # Persistence mirror written into job.json (never the large fields)
    label: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    # Process handle (for cancellation and reaping)
    _process: BaseProcess | None = field(default=None, repr=False)


class JobManager:
    """Manages all docking jobs in this session."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._hub: Any = None

    def bind_hub(self, hub: Any) -> None:
        self._hub = hub

    def _launch(self, job_id: str, entry: Any, worker_params: dict[str, Any]) -> None:
        """Start the worker process and its event reader thread."""
        state = self._jobs[job_id]

        # Create pipe for the worker to send events through
        parent_conn, child_conn = _MP.Pipe(duplex=False)

        process = _MP.Process(
            target=entry,
            args=(worker_params, child_conn),
            daemon=True,
        )
        state._process = process

        # Reader thread bridges pipe events onto the event loop
        reader = threading.Thread(
            target=self._read_events,
            args=(job_id, parent_conn),
            daemon=True,
        )

        process.start()
        child_conn.close()  # Parent doesn't write to child
        reader.start()

    def start_job(self, params: dict[str, Any]) -> str:
        """Spawn a new docking job and return its ID."""
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        state = JobState(
            job_id=job_id,
            status="running",
            scoring=params.get("scoring", "vina"),
            label=_job_label(params),
            params=_persistable_params(params),
        )
        self._jobs[job_id] = state

        # Prepare params for the worker
        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _docking_worker_entry, worker_params)
        # Persist "running" immediately: a SIGKILL before the first stage
        # change must still leave an index the next startup can reconcile.
        self._persist(state)

        log.info("started docking job %s (pid=%s)", job_id, state._process and state._process.pid)
        return job_id

    def start_batch_job(self, params: dict[str, Any]) -> str:
        """Spawn a new batch docking job and return its ID."""
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        ligands = params.get("ligands", [])
        state = JobState(
            job_id=job_id,
            status="running",
            scoring=params.get("scoring", "vina"),
            is_batch=True,
            total_ligands=len(ligands),
            # No ligand path to name it by; the list renders a batch badge.
            label="",
            params=_persistable_params(params),
        )
        self._jobs[job_id] = state

        # Prepare params for the worker
        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _batch_worker_entry, worker_params)
        self._persist(state)

        log.info("started batch docking job %s (pid=%s)", job_id, state._process and state._process.pid)
        return job_id

    def _read_events(self, job_id: str, conn: Any) -> None:
        """Reader thread: drain events from the worker pipe."""
        try:
            while True:
                try:
                    event = conn.recv()
                except EOFError:
                    break
                except (OSError, ValueError):
                    break

                self._handle_event(job_id, event)
        finally:
            conn.close()
            self._reap(job_id)

    def _persist(self, state: JobState) -> None:
        """Rewrite ``job.json`` for a state the caller does not hold the lock on.

        Takes the lock so the payload is one consistent snapshot (the batch
        list is mutated in place while the run progresses), then hands the
        finished dict to the atomic writer.
        """
        with self._lock:
            payload = _job_json_payload(state)
        _write_job_json(state.job_id, payload)

    def _reap(self, job_id: str) -> None:
        """Join the worker once its event pipe has closed.

        Without this the child is never waited for and piles up as a zombie
        for the lifetime of the server.  A worker that outlived its own pipe
        can no longer report anything, so it is killed rather than left running.
        """
        with self._lock:
            state = self._jobs.get(job_id)
            process = state._process if state is not None else None
        if process is None:
            return
        with _PROC_OPS:
            process.join(timeout=5.0)
            wedged = process.is_alive()
        if wedged:
            log.warning("job %s worker outlived its pipe; killing it", job_id)
            _stop_process(process)

        # A worker that died without a terminal event (crash before bootstrap,
        # OOM kill, ...) must not leave the job "running" for ever.  Cancel has
        # already claimed its own status by the time we get here.
        payload: dict[str, Any] | None = None
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None or state.status != "running":
                return
            state.status = "failed"
            state.error = "worker process exited unexpectedly"
            state.stage = None
            state.artifacts = _collect_job_artifacts(job_id)
            payload = _job_json_payload(state)
        if payload is not None:
            _write_job_json(job_id, payload)
        if self._hub is not None:
            self._hub.publish_threadsafe({
                "jobId": job_id,
                "type": "failed",
                "error": "worker process exited unexpectedly",
            })

    def _handle_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Process a single event from the worker."""
        kind = event.get("type", "")
        payload: dict[str, Any] | None = None

        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return

            if kind == "stage":
                state.stage = event.get("stage")
                if state.is_batch and "totalLigands" in event:
                    state.total_ligands = event["totalLigands"]
            elif kind == "progress":
                state.progress = event.get("percent", 0)
            elif kind == "log":
                line = event.get("line", "")
                state.log.append(line)
                if len(state.log) > 500:
                    state.log = state.log[-500:]
                # The file keeps every line; the in-memory list is the capped
                # view.  Appending here is what a restart can replay.
                _append_job_log(job_id, line)
            elif kind == "batch_progress":
                state.current_ligand = event.get("label", "")
                state.completed_ligands = event.get("completed", 0)
                state.failed_ligands = event.get("failed", 0)
                if state.total_ligands > 0:
                    state.progress = int(
                        (state.completed_ligands + state.failed_ligands)
                        / state.total_ligands * 100
                    )
            elif kind == "ligand_completed":
                state.completed_ligands = event.get("completed", 0)
                state.failed_ligands = event.get("failed", 0)
                state.batch_results.append({
                    "ligandIndex": event.get("ligandIndex", 0),
                    "label": event.get("label", ""),
                    "status": event.get("status", ""),
                    "bestAffinity": event.get("bestAffinity"),
                    "nPoses": event.get("nPoses", 0),
                    "elapsedMs": event.get("elapsedMs"),
                    "outDir": event.get("outDir", ""),
                    "error": event.get("error", ""),
                })
                if state.total_ligands > 0:
                    state.progress = int(
                        (state.completed_ligands + state.failed_ligands)
                        / state.total_ligands * 100
                    )
            elif kind == "completed":
                state.progress = 100
                if state.is_batch:
                    state.batch_results = event.get("results", [])
                    state.completed_ligands = event.get("completed", 0)
                    state.failed_ligands = event.get("failed", 0)
                    if len(state.batch_results) > _BATCH_JSON_LIMIT:
                        _write_batch_csv(job_id, state.batch_results)
                else:
                    state.poses = event.get("poses", [])
                    state.best_affinity = event.get("bestAffinity", 0.0)
                    state.n_poses = event.get("nPoses", 0)
                    state.poses_pdbqt = event.get("posesPdbqt", "")
                    state.poses_sdf = event.get("posesSdf", "")
                    # The pipe carried the only copy of the SDF; writing it
                    # here is what makes a restarted session replay results.
                    _write_poses_sdf(job_id, state.poses_sdf)
                state.elapsed_ms = event.get("elapsedMs")
                state.stage = "done"
                state.artifacts = _collect_job_artifacts(job_id)
                state.status = "completed"  # Set LAST to avoid race with HTTP result endpoint
            elif kind == "failed":
                state.status = "failed"
                state.error = event.get("error", "unknown error")
                state.stage = None
                state.artifacts = _collect_job_artifacts(job_id)

            if kind in _PERSIST_EVENT_KINDS:
                payload = _job_json_payload(state)

        # Write after the lock: the swap itself is atomic, so concurrent
        # writers can only race which snapshot lands last, never corrupt it.
        if payload is not None:
            _write_job_json(job_id, payload)

        # Broadcast to WebSocket clients.  The worker's own event carries the
        # `type` (stage/progress/log/completed/failed); adding a second `type`
        # here would be overwritten by `**event` and leave the client unable to
        # tell a job event from a control frame.
        if self._hub is not None:
            self._hub.publish_threadsafe({
                "jobId": job_id,
                **event,
            })

    def cancel_job(self, job_id: str) -> bool:
        """Kill the worker process for a running job."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None or state.status != "running":
                return False
            process = state._process
            state.status = "cancelled"
            state.stage = None
        _stop_process(process)
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return True
            state.artifacts = _collect_job_artifacts(job_id)
            payload = _job_json_payload(state)
        _write_job_json(job_id, payload)
        return True

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return list(self._jobs.values())

    def restore_history(self) -> None:
        """Rebuild the in-memory job list from ``job.json`` files on disk.

        Called once from the app lifespan, never from ``__init__`` — the
        module singleton is imported at collection time and must not touch
        the filesystem there.  Prep run directories carry no index and are
        skipped silently; a crash between restarts surfaces as ``failed``
        with the interrupted error rather than a job that looks alive.
        """
        try:
            entries = sorted(workspace_root().iterdir())
        except OSError:
            log.warning("could not scan workspace for job history", exc_info=True)
            return
        restored = 0
        for entry in entries:
            if not entry.is_dir():
                continue
            index = entry / JOB_STATE_FILENAME
            if not index.is_file():
                continue  # prep runs and stray directories
            try:
                data = json.loads(index.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                log.warning("skipping unreadable job index %s", index, exc_info=True)
                continue
            if not isinstance(data, dict):
                log.warning("skipping malformed job index %s", index)
                continue
            job_id = str(data.get("jobId") or entry.name)
            state = _state_from_payload(data, job_id)
            with self._lock:
                if job_id in self._jobs:
                    continue  # a live run wins over its own stale index
                self._jobs[job_id] = state
            restored += 1
        if restored:
            log.info("restored %d job(s) from workspace history", restored)

    def shutdown(self) -> None:
        """Terminate all running jobs."""
        payloads: list[dict[str, Any]] = []
        with self._lock:
            processes = [
                state._process
                for state in self._jobs.values()
                if state.status == "running"
            ]
            for state in self._jobs.values():
                if state.status == "running":
                    state.status = "cancelled"
                    payloads.append(_job_json_payload(state))
        for payload in payloads:
            _write_job_json(payload["jobId"], payload)
        for process in processes:
            _stop_process(process)


def _stop_process(process: BaseProcess | None) -> None:
    """Stop a worker process, escalating when SIGTERM is not enough.

    Vina has no cancellation API, so killing the process is the only way to
    stop a run.  Terminate first, give it a moment to shut down, then SIGKILL:
    a wedged worker would otherwise keep burning CPU forever.
    """
    if process is None:
        return
    with _PROC_OPS:
        if not process.is_alive():
            return
        process.terminate()
        process.join(timeout=1.0)
        if process.is_alive():
            process.kill()
            process.join(timeout=2.0)


def _collect_job_artifacts(job_id: str) -> list[dict[str, Any]]:
    """Describe the files the worker left in its job directory.

    Matches the shape ``routers/artifacts.py`` serves so the interface can
    treat job outputs like any other workspace artifact.  The URL form works
    because job directories live under the same root ``/artifacts`` mounts.
    """
    job_dir = workspace_root() / job_id
    artifacts: list[dict[str, Any]] = []
    if not job_dir.is_dir():
        return artifacts
    for file in sorted(job_dir.rglob("*")):
        if not file.is_file():
            continue
        if file.name == JOB_STATE_FILENAME:
            continue  # the index is bookkeeping, not an output of the run
        relative = file.relative_to(job_dir).as_posix()
        artifacts.append({
            "name": file.name,
            "path": str(file),
            "url": f"/artifacts/{job_id}/{relative}",
            "bytes": file.stat().st_size,
            "kind": _ARTIFACT_KINDS.get(file.suffix.lower(), "text"),
        })
    return artifacts


def _job_label(params: dict[str, Any]) -> str:
    """Display name for the jobs list: the ligand file, or an honest fallback."""
    ligand_path = params.get("ligandPath")
    if isinstance(ligand_path, str) and ligand_path:
        return Path(ligand_path).name
    return "ligand"  # an inline PDBQT carries no filename to show


def _persistable_params(params: dict[str, Any]) -> dict[str, Any]:
    """Params for ``job.json`` minus inline structure payloads (§ large-fields).

    The path on disk identifies the same molecule, so the duplicated string
    (which can be megabytes for a library entry) never enters the index.
    """

    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in _INLINE_PDBQT_KEYS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return strip(params)


def _top_batch_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top rows for ``job.json``; the full set lives in the CSV artifact.

    Ties keep completion order (sort is stable) and unscored failures sink
    below every scored ligand instead of pretending to rank.
    """
    if len(results) <= _BATCH_JSON_LIMIT:
        return list(results)
    ranked = sorted(
        results,
        key=lambda r: (r.get("bestAffinity") is None, r.get("bestAffinity") or 0.0),
    )
    return ranked[:_BATCH_JSON_LIMIT]


def _job_json_payload(state: JobState, *, now: float | None = None) -> dict[str, Any]:
    """Serializable mirror of ``JobState`` for ``job.json``.

    Large fields never ride along: the pose PDBQT, the pose SDF and the log
    are artifact files beside the index, addressed by convention.  The copy of
    ``batch_results`` matters — that list is appended to while a batch runs.
    """
    return {
        "schemaVersion": 1,
        "jobId": state.job_id,
        "status": state.status,
        "progress": state.progress,
        "stage": state.stage,
        "error": state.error,
        "elapsedMs": state.elapsed_ms,
        "scoring": state.scoring,
        "createdAt": state.created_at,
        "updatedAt": time.time() if now is None else now,
        "label": state.label,
        "params": state.params,
        "poses": list(state.poses),
        "bestAffinity": state.best_affinity,
        "nPoses": state.n_poses,
        "isBatch": state.is_batch,
        "totalLigands": state.total_ligands,
        "completedLigands": state.completed_ligands,
        "failedLigands": state.failed_ligands,
        "batchResults": _top_batch_results(state.batch_results),
        "batchResultsTruncated": len(state.batch_results) > _BATCH_JSON_LIMIT,
        "artifacts": list(state.artifacts),
    }


def _write_job_json(job_id: str, payload: dict[str, Any]) -> None:
    """Rewrite the job index atomically, fsync once.

    The tmp-file swap means a crash mid-write leaves the previous index
    intact; one fsync is enough for the stage/terminal durability the
    recovery rules promise (TASK-07 §4.2).  A failed persist must never
    break the run itself — it degrades to a warning.
    """
    try:
        path = job_state_path(job_id)
        if not path.parent.is_dir():
            # Only a real run creates the job directory. A JobState that was
            # injected without one must never conjure a workspace dir — that
            # would leave an index behind for the next restore to resurrect.
            return
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except OSError:
        log.warning("could not persist job index for %s", job_id, exc_info=True)


def _write_poses_sdf(job_id: str, sdf: str) -> None:
    """Persist the pose SDF as an artifact so a restart can replay results.

    The worker delivers the SDF through the pipe and nothing wrote it to
    disk before — which is exactly what an in-memory-only session loses.
    """
    if not sdf:
        return
    try:
        target = workspace_root() / job_id / POSES_SDF_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sdf, encoding="utf-8")
    except OSError:
        log.warning("could not write poses SDF for job %s", job_id, exc_info=True)


def _write_batch_csv(job_id: str, results: list[dict[str, Any]]) -> None:
    """Keep the full batch ranking as a CSV artifact next to the index."""
    try:
        target = workspace_root() / job_id / BATCH_RESULTS_CSV_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(batch_results_csv_text(results), encoding="utf-8")
    except OSError:
        log.warning("could not write batch CSV for job %s", job_id, exc_info=True)


def _append_job_log(job_id: str, line: str) -> None:
    """Append one worker line to the job's log file (replayed after restart)."""
    try:
        target = job_log_path(job_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        log.warning("could not append log line for job %s", job_id, exc_info=True)


def _read_job_text(job_id: str, name: str) -> str:
    """Read one artifact beside the index; any IO problem degrades to empty."""
    try:
        return (workspace_root() / job_id / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_job_log(job_id: str) -> list[str]:
    """Last 500 lines of the replayed log (same cap as the live ring buffer)."""
    text = _read_job_text(job_id, JOB_LOG_FILENAME)
    if not text:
        return []
    return text.splitlines()[-500:]


def _read_batch_csv(job_id: str) -> list[dict[str, Any]] | None:
    """Parse the full-ranking artifact back into batch row dicts.

    ``None`` means no (readable) CSV — callers then fall back to the top
    slice stored in ``job.json``.
    """
    text = _read_job_text(job_id, BATCH_RESULTS_CSV_FILENAME)
    if not text:
        return None
    rows: list[dict[str, Any]] = []
    try:
        for raw in csv.DictReader(io.StringIO(text)):
            affinity: float | None = None
            raw_affinity = (raw.get("best_affinity_kcal_mol") or "").strip()
            if raw_affinity:
                try:
                    affinity = float(raw_affinity)
                except ValueError:
                    affinity = None
            rows.append({
                "ligandIndex": int(raw.get("ligand_index") or 0),
                "label": raw.get("label") or "",
                "status": raw.get("status") or "",
                "bestAffinity": affinity,
                "nPoses": int(raw.get("pose_count") or 0),
                "elapsedMs": None,
                "outDir": "",
                "error": raw.get("error") or "",
            })
    except (ValueError, csv.Error):
        log.warning("batch CSV for job %s is unreadable", job_id, exc_info=True)
        return None
    return rows


def _state_from_payload(data: dict[str, Any], job_id: str) -> JobState:
    """Build a ``JobState`` from a persisted index, hydrating by convention.

    The large fields never ride in the JSON, so a restored job reads them
    back from the artifacts written at completion (TASK-07 §4.2).
    """
    status = data.get("status", "failed")
    if status not in {"queued", "running", "completed", "failed", "cancelled"}:
        status = "failed"
    interrupted = status in {"running", "queued"}
    if interrupted:
        status = "failed"  # this process was not running when the file was written

    state = JobState(
        job_id=job_id,
        status=status,
        progress=int(data.get("progress") or 0),
        stage=None if interrupted else data.get("stage"),
        error=(
            "session restarted while the job was running"
            if interrupted
            else data.get("error")
        ),
        elapsed_ms=data.get("elapsedMs"),
        scoring=str(data.get("scoring") or "vina"),
        created_at=float(data.get("createdAt") or time.time()),
        poses=list(data.get("poses") or []),
        best_affinity=float(data.get("bestAffinity") or 0.0),
        n_poses=int(data.get("nPoses") or 0),
        is_batch=bool(data.get("isBatch")),
        total_ligands=int(data.get("totalLigands") or 0),
        completed_ligands=int(data.get("completedLigands") or 0),
        failed_ligands=int(data.get("failedLigands") or 0),
        label=str(data.get("label") or ""),
        params=dict(data.get("params") or {}),
    )

    if state.is_batch:
        from_csv = _read_batch_csv(job_id)
        # The CSV artifact exists only for truncated batches; otherwise the
        # index itself already holds every row.
        state.batch_results = from_csv if from_csv else list(data.get("batchResults") or [])
    elif state.status == "completed":
        state.poses_pdbqt = _read_job_text(job_id, "poses.pdbqt")
        state.poses_sdf = _read_job_text(job_id, POSES_SDF_FILENAME)

    state.log = _read_job_log(job_id)
    state.artifacts = (
        # Interrupted run: the on-disk set is all there ever will be.
        _collect_job_artifacts(job_id)
        if interrupted
        else [a for a in (data.get("artifacts") or []) if isinstance(a, dict)]
    )
    return state


def batch_results_csv_text(batch_results: list[dict[str, Any]]) -> str:
    """Render batch rows as CSV text for download and for the full-ranking
    artifact above the ``job.json`` row cap.

    Moved here from the router so the index writer and the export endpoint
    share one definition.  ``pose_count`` reads ``nPoses``: the rows have
    never carried an ``energies`` list, so counting that always wrote 0.
    """
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


def _docking_worker_entry(params: dict[str, Any], pipe: Any) -> None:
    """Entry point for the spawned child process."""
    from vinastudio.core.worker import docking_worker

    docking_worker(params, pipe)


def _batch_worker_entry(params: dict[str, Any], pipe: Any) -> None:
    """Entry point for a batch docking child process."""
    from vinastudio.core.worker import batch_docking_worker

    batch_docking_worker(params, pipe)


#: Module-level singleton shared across the application.
manager = JobManager()
