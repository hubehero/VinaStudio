"""In-memory job manager for docking runs.

Each job owns a spawned child process, a reader thread that bridges pipe events
onto the asyncio loop, and an artifact directory under the workspace's
``jobs/`` folder (the same root ``/artifacts`` serves).  Cancellation kills the
child process.

The module-level ``manager`` singleton is the single entry point.
"""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
import uuid
from dataclasses import dataclass, field
from multiprocessing.process import BaseProcess
from typing import Any, Literal

from vinastudio.core.paths import workspace_root

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
}

#: Serialises join/kill on worker processes.  ``cancel_job`` (request thread)
#: and ``_reap`` (reader thread) drive the same child; concurrent ``join``s
#: race ``waitpid`` and can make ``is_alive()`` lie — which would send SIGTERM
#: to a pid that may already have been reused.
_PROC_OPS = threading.Lock()


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

        state = JobState(job_id=job_id, status="running", scoring=params.get("scoring", "vina"))
        self._jobs[job_id] = state

        # Prepare params for the worker
        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _docking_worker_entry, worker_params)

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
        )
        self._jobs[job_id] = state

        # Prepare params for the worker
        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _batch_worker_entry, worker_params)

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
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None or state.status != "running":
                return
            state.status = "failed"
            state.error = "worker process exited unexpectedly"
            state.stage = None
            state.artifacts = _collect_job_artifacts(job_id)
        if self._hub is not None:
            self._hub.publish_threadsafe({
                "jobId": job_id,
                "type": "failed",
                "error": "worker process exited unexpectedly",
            })

    def _handle_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Process a single event from the worker."""
        kind = event.get("type", "")

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
                state.status = "completed"
                state.progress = 100
                if state.is_batch:
                    state.batch_results = event.get("results", [])
                    state.completed_ligands = event.get("completed", 0)
                    state.failed_ligands = event.get("failed", 0)
                else:
                    state.poses = event.get("poses", [])
                    state.best_affinity = event.get("bestAffinity", 0.0)
                    state.n_poses = event.get("nPoses", 0)
                    state.poses_pdbqt = event.get("posesPdbqt", "")
                    state.poses_sdf = event.get("posesSdf", "")
                state.elapsed_ms = event.get("elapsedMs")
                state.stage = "done"
                state.artifacts = _collect_job_artifacts(job_id)
            elif kind == "failed":
                state.status = "failed"
                state.error = event.get("error", "unknown error")
                state.stage = None
                state.artifacts = _collect_job_artifacts(job_id)

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
            if state is not None:
                state.artifacts = _collect_job_artifacts(job_id)
        return True

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return list(self._jobs.values())

    def shutdown(self) -> None:
        """Terminate all running jobs."""
        with self._lock:
            processes = [
                state._process
                for state in self._jobs.values()
                if state.status == "running"
            ]
            for state in self._jobs.values():
                if state.status == "running":
                    state.status = "cancelled"
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
        relative = file.relative_to(job_dir).as_posix()
        artifacts.append({
            "name": file.name,
            "path": str(file),
            "url": f"/artifacts/{job_id}/{relative}",
            "bytes": file.stat().st_size,
            "kind": _ARTIFACT_KINDS.get(file.suffix.lower(), "text"),
        })
    return artifacts


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
