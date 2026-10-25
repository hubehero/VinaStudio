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
import math
import multiprocessing
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Literal

from vinastudio.core import results_db
from vinastudio.core.paths import (
    BATCH_RESULTS_CSV_FILENAME,
    JOB_LOG_FILENAME,
    JOB_STATE_FILENAME,
    POSES_SDF_FILENAME,
    SCREENING_JSONL_FILENAME,
    SITES_JSONL_FILENAME,
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
#: carry; the path on disk identifies the same molecule.  Both casings are
#: stripped: production single-ligand params are snake_case (routers/docking
#: writes ``ligand_pdbqt_string``) while API/batch payloads are camelCase — a
#: one-sided set let the real inline PDBQT through into ``job.json`` (TASK-27 B1).
_INLINE_PDBQT_KEYS = frozenset({
    "ligandPdbqtString", "receptorPdbqtString", "pdbqtString",
    "ligand_pdbqt_string", "receptor_pdbqt_string", "pdbqt_string",
})

#: Persist the index when one of these event kinds mutates the state.
_PERSIST_EVENT_KINDS = frozenset({"stage", "completed", "failed"})


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress: int = 0
    stage: str | None = None
    log: list[str] = field(default_factory=list)
    # Restored jobs defer their log/poses reads to the first get_job()
    # (TASK-28 P2-A): startup touches every index, the API touches few.
    needs_hydration: bool = field(default=False, repr=False)
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
    # Screening-specific (TASK-13): rows live in screening.jsonl, never in
    # batch_results (§8), and the run-level best is the min over completed
    # molecules — None until one lands, so the summary can say "nothing yet".
    is_screening: bool = False
    screening_best: float | None = None
    # Ensemble: one ligand docked into several receptor conformations. Rows
    # stay in the index (small) and the terminal event carries the winning
    # conformation's poses.
    is_ensemble: bool = False
    ensemble_results: list[dict[str, Any]] = field(default_factory=list)
    best_receptor: str | None = None
    # Site screening (S2): one ligand docked into several candidate boxes. Rows
    # live in ``sites.jsonl``; the box counters reuse the batch generics
    # (``total_ligands`` / ``completed_ligands`` / ``failed_ligands``) because
    # they mean "work items", which is exactly what boxes are here.
    is_site_screening: bool = False
    # Persistence mirror written into job.json (never the large fields)
    label: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    # Worker group (for cancellation and reaping): one entry per shard
    # process — a batch job runs N children that all feed this one state.
    _processes: list[BaseProcess] = field(default_factory=list, repr=False)
    # Reader bookkeeping: pipes opened vs pipes drained.  The last reader to
    # close settles the job, so the counters must live on the state, not the
    # thread.  total defaults to 1 so an injected state still settles like a
    # single run.
    _readers_total: int = field(default=1, repr=False)
    _readers_done: int = field(default=0, repr=False)


class JobManager:
    """Manages all docking jobs in this session."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._hub: Any = None

    def bind_hub(self, hub: Any) -> None:
        self._hub = hub

    def _launch(self, job_id: str, entry: Any, worker_params_list: list[dict[str, Any]]) -> None:
        """Start one spawned worker per params entry, one reader per pipe.

        The whole group is registered on the state before any ``start()``: a
        cancel or shutdown racing this window must still see every process it
        has to kill, and a reader must never decrement a counter that was not
        initialised yet.
        """
        state = self._jobs[job_id]

        # One pipe per worker: events stay independent, the state does not.
        prepared: list[tuple[BaseProcess, Any, Any]] = []
        for worker_params in worker_params_list:
            parent_conn, child_conn = _MP.Pipe(duplex=False)
            process = _MP.Process(
                target=entry,
                args=(worker_params, child_conn),
                daemon=True,
            )
            prepared.append((process, parent_conn, child_conn))

        with self._lock:
            state._processes = [process for process, _, _ in prepared]
            state._readers_total = len(prepared)
            state._readers_done = 0

        for process, parent_conn, child_conn in prepared:
            process.start()
            child_conn.close()  # Parent doesn't write to child
            # Reader thread bridges pipe events onto the event loop
            threading.Thread(
                target=self._read_events,
                args=(job_id, parent_conn, process),
                daemon=True,
            ).start()

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

        self._launch(job_id, _docking_worker_entry, [worker_params])
        # Persist "running" immediately: a SIGKILL before the first stage
        # change must still leave an index the next startup can reconcile.
        self._persist(state)

        log.info(
            "started docking job %s (pid=%s)",
            job_id,
            state._processes[0].pid if state._processes else None,
        )
        return job_id

    def start_batch_job(self, params: dict[str, Any]) -> str:
        """Spawn a new batch docking job and return its ID."""
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        ligands = params.get("ligands", [])
        shard_count = _batch_shard_count(params, len(ligands))
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

        # Prepare params shared by every shard. No map pre-computation here:
        # vina's load_maps path segfaults under set_receptor (upstream
        # expects maps without a receptor), so shards compute maps per ligand
        # — the pre-bf86a79 behaviour (TASK-14 Q1 ruling, 2026-10-08).
        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        # Static sharding: shard i docks ligands[i::shard_count], keeping the
        # original ligand index for events and on-disk names (TASK-14 §4.1).
        shards = [
            {**worker_params, "shard_index": index, "shard_count": shard_count}
            for index in range(shard_count)
        ]
        self._launch(job_id, _batch_worker_entry, shards)
        self._persist(state)

        log.info(
            "started batch docking job %s (workers=%d pids=%s)",
            job_id,
            len(state._processes),
            [process.pid for process in state._processes],
        )
        return job_id

    def start_screening_job(self, params: dict[str, Any]) -> str:
        """Spawn a virtual screening job over a library (TASK-13 §4.2).

        Settles through the batch parent path (``is_batch``) — same group
        cancel, same server-side counters — but per-molecule rows go to
        ``screening.jsonl`` and never into ``batch_results`` (§8).
        ``params["entries"]`` is the full library roster (``index`` + ``name``);
        sharding slices it exactly like a batch.
        """
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        entries = params.get("entries", [])
        shard_count = _batch_shard_count(params, len(entries))
        state = JobState(
            job_id=job_id,
            status="running",
            scoring=params.get("scoring", "vina"),
            is_batch=True,
            is_screening=True,
            total_ligands=len(entries),
            # The library name is what the runs list shows.
            label=str(params.get("library") or ""),
            params=_persistable_params(params),
        )
        self._jobs[job_id] = state

        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        shards = [
            {**worker_params, "shard_index": index, "shard_count": shard_count}
            for index in range(shard_count)
        ]
        self._launch(job_id, _screening_worker_entry, shards)
        self._persist(state)

        log.info(
            "started screening job %s (library=%s workers=%d)",
            job_id,
            state.label,
            len(state._processes),
        )
        return job_id

    def start_ensemble_job(self, params: dict[str, Any]) -> str:
        """Spawn an ensemble: one ligand against several receptor conformations.

        A single worker keeps the ranking and the winning pose in one place;
        the number of conformers is small. The box is shared because the
        conformers must be in the same coordinate frame.
        """
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        receptors = list(params.get("receptors", []))
        state = JobState(
            job_id=job_id,
            status="running",
            scoring=params.get("scoring", "vina"),
            is_ensemble=True,
            total_ligands=len(receptors),
            label=str(params.get("label") or "ensemble"),
            params=_persistable_params(params),
        )
        self._jobs[job_id] = state

        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _ensemble_worker_entry, [worker_params])
        self._persist(state)
        log.info(
            "started ensemble job %s (%d receptor conformations)",
            job_id,
            len(receptors),
        )
        return job_id

    def start_site_screening_job(self, params: dict[str, Any]) -> str:
        """Spawn a site screen: one ligand docked into each candidate box (S2).

        A single worker on purpose. The detector returns a handful of boxes, and
        a sweep is a *ranking* problem — splitting it across processes would buy
        nothing and complicate one-shard-per-box cancellation. ``params["candidates"]``
        is the list of ``{index, label, center, size}`` boxes to try.
        """
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_root() / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        candidates = list(params.get("candidates", []))
        state = JobState(
            job_id=job_id,
            status="running",
            scoring=params.get("scoring", "vina"),
            is_site_screening=True,
            total_ligands=len(candidates),
            label=str(params.get("label") or "site screen"),
            params=_persistable_params(params),
        )
        self._jobs[job_id] = state

        worker_params = dict(params)
        worker_params["job_id"] = job_id
        worker_params["output_dir"] = str(job_dir)

        self._launch(job_id, _site_screening_worker_entry, [worker_params])
        self._persist(state)

        log.info(
            "started site screening job %s (%d candidate boxes)",
            job_id,
            len(candidates),
        )
        return job_id

    def resume_screening_job(self, job_id: str, skip: set[int]) -> JobState | None:
        """Relaunch the molecules of a screening run that are not in ``skip``.

        Counters are recomputed from the jsonl, not trusted from memory: after
        a restart ``job.json`` only ever saw the last stage event, so its
        counters lag the append-only rows (which are the resume truth).
        Returns None for an unknown job; the router maps status conflicts.
        """
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return None
            entries = [
                entry
                for entry in (state.params.get("entries") or [])
                if _entry_index(entry) not in skip
            ]
            _, done, failed, _ = screening_jsonl_progress(job_id)
            state.completed_ligands = done
            state.failed_ligands = failed
            if state.total_ligands > 0:
                state.progress = int((done + failed) / state.total_ligands * 100)
            state.status = "running"
            state.error = None
            state.stage = None
            # state.params keeps the full roster — a second resume must still
            # know about molecules this one is about to re-run.
            worker_params = {
                **state.params,
                "entries": entries,
                "job_id": job_id,
                "output_dir": str(workspace_root() / job_id),
            }
            shard_count = _batch_shard_count(worker_params, len(entries))
            shards = [
                {**worker_params, "shard_index": index, "shard_count": shard_count}
                for index in range(shard_count)
            ]
        # _launch and _persist both take the lock; never hold it across them.
        self._launch(job_id, _screening_worker_entry, shards)
        self._persist(state)
        log.info(
            "resumed screening job %s (skip=%d remaining=%d workers=%d)",
            job_id,
            len(skip),
            len(entries),
            len(state._processes),
        )
        return state

    def _read_events(self, job_id: str, conn: Any, process: BaseProcess) -> None:
        """Reader thread: drain events from one worker pipe, then reap it."""
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
            self._reap(job_id, process)

    def _persist(self, state: JobState) -> None:
        """Rewrite ``job.json`` for a state the caller does not hold the lock on.

        Takes the lock so the payload is one consistent snapshot (the batch
        list is mutated in place while the run progresses), then hands the
        finished dict to the atomic writer.
        """
        with self._lock:
            payload = _job_json_payload(state)
            batch_rows = list(state.batch_results)
        # Full rows (not the payload's top slice) so the per-ligand index
        # never silently loses molecules past the 100-row cap (§4.7).
        _write_job_json(state.job_id, payload, ligand_rows=batch_rows)

    def _reap(self, job_id: str, process: BaseProcess) -> None:
        """Join one worker once its event pipe has closed, then settle the job.

        Each reader joins its own child — a batch group holds several — and
        bumps the state's reader counter on the way out.  Without the join the
        child is never waited for and piles up as a zombie for the lifetime of
        the server; a worker that outlived its own pipe can no longer report
        anything, so it is killed rather than left running.  Only the reader
        that closes the last pipe of the group may decide the job is over.
        """
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
        completed_event: dict[str, Any] | None = None
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            state._readers_done += 1
            if state._readers_done < state._readers_total:
                return  # other workers of this group still hold their pipes
            if state.status != "running":
                return
            # Batch jobs settle here: the parent owns the job's single
            # completion event (TASK-14 §4.3).  A partial group, a crashed
            # shard or a single-ligand job falls through to the failed path —
            # same semantics a lone worker dying without its terminal event.
            settled = state.is_batch and (
                state.completed_ligands + state.failed_ligands
                >= state.total_ligands
                and all(process.exitcode == 0 for process in state._processes)
            )
            if settled:
                completed_event = {
                    "type": "completed",
                    # Shards finish out of order; rows land index-sorted so
                    # index/CSV readers never see completion jitter (§4.3).
                    "results": sorted(
                        state.batch_results,
                        key=lambda row: row.get("ligandIndex", 0),
                    ),
                    "total": state.total_ligands,
                    "completed": state.completed_ligands,
                    "failed": state.failed_ligands,
                    "elapsedMs": int((time.time() - state.created_at) * 1000),
                }
            else:
                state.status = "failed"
                state.error = "worker process exited unexpectedly"
                state.stage = None
                state.artifacts = _collect_job_artifacts(job_id)
                payload = _job_json_payload(state)
        if completed_event is not None:
            # Reuse the event path so persist, the CSV cap and the WS
            # broadcast stay one implementation — and fire exactly once.
            self._handle_event(job_id, completed_event)
            return
        if payload is not None:
            _write_job_json(job_id, payload, ligand_rows=list(state.batch_results))
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
                # Multi-item jobs derive progress from completed work items;
                # a Vina stdout scale from one child must not move the whole
                # batch/screening/ensemble bar to 100.
                if not (
                    state.is_batch
                    or state.is_screening
                    or state.is_ensemble
                    or state.is_site_screening
                ):
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
                # Label only: the counters that ride along are shard-local
                # values and meaningless once N workers report (TASK-14 §4.3).
                state.current_ligand = event.get("label", "")
            elif kind == "ligand_completed":
                # The server owns the counters — one increment per terminal
                # event, under the same lock every reader holds, so concurrent
                # shards can neither lose nor double-count a ligand.
                if event.get("status") == "completed":
                    state.completed_ligands += 1
                else:
                    state.failed_ligands += 1
                if state.is_screening:
                    # Single writer: this lock serialises every reader thread,
                    # so jsonl lines can never interleave (TASK-13 §4.2).
                    _append_screening_jsonl(job_id, _screening_row(event))
                    affinity = event.get("bestAffinity")
                    if event.get("status") == "completed" and isinstance(affinity, (int, float)):
                        if state.screening_best is None:
                            state.screening_best = float(affinity)
                        else:
                            state.screening_best = min(state.screening_best, float(affinity))
                else:
                    state.batch_results.append({
                        "ligandIndex": event.get("ligandIndex", 0),
                        "label": event.get("label", ""),
                        "status": event.get("status", ""),
                        "bestAffinity": event.get("bestAffinity"),
                        "nPoses": event.get("nPoses", 0),
                        "elapsedMs": event.get("elapsedMs"),
                        "outDir": event.get("outDir", ""),
                        "error": event.get("error", ""),
                        # TASK-10 handover: descriptors ride every row, null
                        # when nothing parsed (CSV renders them as empty).
                        "qed": event.get("qed"),
                        "lipinskiViolations": event.get("lipinskiViolations"),
                        "smiles": event.get("smiles"),
                    })
                if state.total_ligands > 0:
                    state.progress = int(
                        (state.completed_ligands + state.failed_ligands)
                        / state.total_ligands * 100
                    )
            elif kind == "ensemble_progress":
                state.current_ligand = event.get("label", "")
            elif kind == "ensemble_completed":
                if event.get("status") == "completed":
                    state.completed_ligands += 1
                else:
                    state.failed_ligands += 1
                state.ensemble_results.append({
                    "receptorIndex": event.get("receptorIndex", 0),
                    "label": event.get("label", ""),
                    "receptorPath": event.get("receptorPath", ""),
                    "status": event.get("status", "failed"),
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
            elif kind == "site_progress":
                # Label only, exactly like ``batch_progress``: the running box
                # is display state, not a counter.
                state.current_ligand = event.get("label", "")
            elif kind == "site_completed":
                # One ligand, many boxes: the counters are box counters (see
                # ``JobState.is_site_screening``), and the append-only rows are
                # the ranking the sites endpoint serves.
                if event.get("status") == "completed":
                    state.completed_ligands += 1
                else:
                    state.failed_ligands += 1
                _append_site_jsonl(job_id, _site_row(event))
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
                    if state.is_ensemble:
                        state.best_receptor = event.get("bestReceptor")
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
            current = self._jobs.get(job_id)
            _write_job_json(
                job_id,
                payload,
                ligand_rows=list(current.batch_results) if current is not None else None,
            )

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
        """Kill every worker process of a running job, then settle the index."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None or state.status != "running":
                return False
            processes = list(state._processes)
            state.status = "cancelled"
            state.stage = None
        # All children must be dead before the terminal snapshot lands: a
        # shard still alive would append rows to a job.json already written
        # as cancelled (TASK-14 §4.4 — stop first, write after).
        for process in processes:
            _stop_process(process)
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return True
            state.artifacts = _collect_job_artifacts(job_id)
            payload = _job_json_payload(state)
            batch_rows = list(state.batch_results)
        _write_job_json(job_id, payload, ligand_rows=batch_rows)
        return True

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state is not None and state.needs_hydration:
                # First access after restore fills the large text fields.
                # Hydration holds the lock so two concurrent first reads
                # cannot race; it costs one pass per restored job, ever.
                _hydrate_state(state)
            return state

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return list(self._jobs.values())

    def register_imported(self, state: JobState) -> None:
        """Expose a completed job restored from a result bundle.

        The caller has already written the payload files into the job
        directory.  Registration is in-memory plus the same ``job.json`` write
        funnel a normal completion uses, so the imported run also lands in the
        results index and survives a restart.  It never starts a worker.
        """
        with self._lock:
            if state.job_id in self._jobs:
                raise ValueError(f"job {state.job_id} already exists")
            self._jobs[state.job_id] = state
        _write_job_json(state.job_id, _job_json_payload(state))

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
        # What each readable index holds on disk *after* this pass (the
        # terminalising write below rewrites interrupted payloads) — handed
        # to backfill so the payloads are parsed once, not twice (P2-A).
        known: list[tuple[Path, dict[str, Any]]] = []
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
            interrupted = data.get("status") in {"running", "queued"}
            state = _state_from_payload(data, job_id)
            with self._lock:
                if job_id in self._jobs:
                    continue  # a live run wins over its own stale index
                self._jobs[job_id] = state
            if interrupted:
                # A SIGKILL left the index claiming a live run.  Marking the
                # memory failed is not enough: backfill() below skips any
                # non-terminal job.json, so the run would never reach the
                # results index.  Terminalising through the write funnel also
                # ingests the payload (with rows, when a complete source
                # exists), and the backfill afterwards skips it as indexed.
                payload = _job_json_payload(state)
                # The restored batch_results may be only the top slice of a
                # truncated index (an interrupted run never wrote its CSV):
                # carry the original flag so the slice never masquerades as
                # the complete ranking (TASK-27 §4.2).
                payload["batchResultsTruncated"] = bool(
                    payload["batchResultsTruncated"]
                ) or bool(data.get("batchResultsTruncated"))
                _write_job_json(
                    job_id,
                    payload,
                    ligand_rows=results_db.batch_ligand_rows(data),
                )
                known.append((index, payload))
            else:
                known.append((index, data))
            restored += 1
        if restored:
            log.info("restored %d job(s) from workspace history", restored)
        # Repair runs whose job.json exists but whose row never landed (a
        # crash between the terminal write and the ingest).  backfill() skips
        # what is already indexed, so running it every launch is idempotent.
        try:
            results_db.backfill(known=known)
        except Exception:
            log.warning("results backfill failed", exc_info=True)

    def shutdown(self) -> None:
        """Terminate all running jobs."""
        pending: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        with self._lock:
            processes: list[BaseProcess] = []
            for state in self._jobs.values():
                if state.status == "running":
                    state.status = "cancelled"
                    pending.append(
                        (_job_json_payload(state), list(state.batch_results))
                    )
                    processes.extend(state._processes)
        for payload, rows in pending:
            _write_job_json(payload["jobId"], payload, ligand_rows=rows)
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


def _batch_shard_count(params: dict[str, Any], n_ligands: int) -> int:
    """Worker count for a batch job: request, hard cap 4, env cap, memory cap.

    The estimate models the Vina map grids — the allocation that dominates a
    worker — as ``prod(ceil(edge/0.375)) cells x 6 maps x float64 x 4x
    headroom`` with a 256 MiB per-worker floor and an 8 GiB total budget
    (TASK-14 §4.2).  The coefficients are provisional: they are reported
    verbatim so a later calibration can replace them against measurements.
    Caps only ever lower the request; the final count is what each shard gets
    as ``shard_count``.
    """
    requested = params.get("parallelism")
    if not isinstance(requested, int) or requested < 1:
        requested = max(1, (os.cpu_count() or 1) - 1)

    count = min(requested, 4, max(1, n_ligands))

    env_raw = os.environ.get("VINASTUDIO_MAX_PARALLEL", "")
    if env_raw:
        try:
            env_cap = int(env_raw)
        except ValueError:
            env_cap = 0
        if env_cap >= 1:
            count = min(count, env_cap)
        else:
            log.warning("VINASTUDIO_MAX_PARALLEL=%r ignored (need an int >= 1)", env_raw)

    try:
        cells = 1
        for edge in params.get("size") or [20, 20, 20]:
            cells *= math.ceil(float(edge) / 0.375)
        est_bytes = cells * 6 * 8 * 4
    except (TypeError, ValueError, OverflowError):
        est_bytes = 0  # malformed size: fall through to the 256 MiB floor
    mem_cap = max(1, (8 * 1024**3) // max(est_bytes, 256 * 1024**2))
    count = min(count, mem_cap)

    if count < min(requested, 4, max(1, n_ligands)):
        log.warning(
            "batch shard count capped to %d (request=%d, ligands=%d, "
            "memory cap=%d, est per-worker bytes=%d)",
            count, requested, n_ligands, mem_cap, est_bytes,
        )
    return count


def _entry_index(entry: Any) -> int:
    """Library roster ordinal, or -1 for a malformed entry."""
    try:
        return int(entry.get("index"))  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        return -1


def _screening_row(event: dict[str, Any]) -> dict[str, Any]:
    """One append-only jsonl row; key set verbatim from TASK-13 §4.2."""
    affinity = event.get("bestAffinity")
    qed = event.get("qed")
    lipinski = event.get("lipinskiViolations")
    n_poses = event.get("nPoses")
    elapsed = event.get("elapsedMs")
    return {
        "i": int(event.get("ligandIndex") or 0),
        "name": str(event.get("label") or ""),
        "status": "completed" if event.get("status") == "completed" else "failed",
        "affinity": float(affinity) if isinstance(affinity, (int, float)) else None,
        "nPoses": int(n_poses) if isinstance(n_poses, (int, float)) else None,
        "elapsedMs": int(elapsed) if isinstance(elapsed, (int, float)) else None,
        "qed": float(qed) if isinstance(qed, (int, float)) else None,
        "lipinski": int(lipinski) if isinstance(lipinski, (int, float)) else None,
        "smiles": event.get("smiles") if isinstance(event.get("smiles"), str) else None,
        "outDir": event.get("outDir") or None,
        "error": event.get("error") or None,
        "ts": int(time.time() * 1000),
    }


def _append_screening_jsonl(job_id: str, row: dict[str, Any]) -> None:
    """Append one terminal row; called under the manager lock (single writer)."""
    try:
        target = workspace_root() / job_id / SCREENING_JSONL_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("could not append screening row for job %s", job_id, exc_info=True)


def read_screening_rows(job_id: str) -> list[dict[str, Any]]:
    """Parsed terminal rows of ``screening.jsonl``; unreadable file → []."""
    try:
        text = (workspace_root() / job_id / SCREENING_JSONL_FILENAME).read_text(
            encoding="utf-8"
        )
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("status") in {"completed", "failed"}:
            rows.append(row)
    return rows


def screening_jsonl_progress(job_id: str) -> tuple[set[int], int, int, float | None]:
    """``(skip set, completed, failed, best)`` — the resume truth for one run.

    The jsonl, not ``job.json``'s counters, is what a restart can trust: the
    index is only rewritten on stage/terminal events, so its counters lag an
    interrupted run while the append-only rows never do (TASK-13 §4.2).
    ``best`` is the run-level minimum affinity across completed rows.
    """
    rows = read_screening_rows(job_id)
    skip = {row["i"] for row in rows if isinstance(row.get("i"), int)}
    done = sum(1 for row in rows if row.get("status") == "completed")
    affinities = [
        float(row["affinity"])
        for row in rows
        if isinstance(row.get("affinity"), (int, float))
    ]
    return skip, done, len(rows) - done, (min(affinities) if affinities else None)


def _site_row(event: dict[str, Any]) -> dict[str, Any]:
    """One append-only row of ``sites.jsonl``: the result of one candidate box.

    ``affinity`` is this box's best (most negative) pose, or ``None`` when the
    box produced no pose at all — a null is *unrankable*, not a score of zero.
    """
    affinity = event.get("bestAffinity")
    n_poses = event.get("nPoses")
    elapsed = event.get("elapsedMs")
    return {
        "i": int(event.get("siteIndex") or 0),
        "label": str(event.get("label") or ""),
        "status": "completed" if event.get("status") == "completed" else "failed",
        "affinity": float(affinity) if isinstance(affinity, (int, float)) else None,
        "nPoses": int(n_poses) if isinstance(n_poses, (int, float)) else None,
        "elapsedMs": int(elapsed) if isinstance(elapsed, (int, float)) else None,
        "error": event.get("error") or None,
        "ts": int(time.time() * 1000),
    }


def _append_site_jsonl(job_id: str, row: dict[str, Any]) -> None:
    """Append one box row; called under the manager lock (single writer)."""
    try:
        target = workspace_root() / job_id / SITES_JSONL_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("could not append site row for job %s", job_id, exc_info=True)


def read_site_rows(job_id: str) -> list[dict[str, Any]]:
    """Parsed candidate rows of ``sites.jsonl``; unreadable file → []."""
    try:
        text = (workspace_root() / job_id / SITES_JSONL_FILENAME).read_text(
            encoding="utf-8"
        )
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("status") in {"completed", "failed"}:
            rows.append(row)
    return rows


def _job_label(params: dict[str, Any]) -> str:
    """Display name for the jobs list: the ligand file, or an honest fallback.

    Snake first: production single-ligand params are snake_case
    (``routers/docking`` writes ``ligand_path``), so a camel-only lookup
    always fell back to "ligand"; camel stays accepted for API payloads
    and the existing fixtures (TASK-27 B1).
    """
    for key in ("ligand_path", "ligandPath"):
        ligand_path = params.get(key)
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
        "bestAffinity": state.screening_best if state.is_screening else state.best_affinity,
        "nPoses": state.n_poses,
        "isBatch": state.is_batch,
        "isScreening": state.is_screening,
        "isSiteScreening": state.is_site_screening,
        "isEnsemble": state.is_ensemble,
        "bestReceptor": state.best_receptor,
        "ensembleResults": list(state.ensemble_results),
        "totalLigands": state.total_ligands,
        "completedLigands": state.completed_ligands,
        "failedLigands": state.failed_ligands,
        "batchResults": _top_batch_results(state.batch_results),
        "batchResultsTruncated": len(state.batch_results) > _BATCH_JSON_LIMIT,
        "artifacts": list(state.artifacts),
    }


def _write_job_json(
    job_id: str,
    payload: dict[str, Any],
    *,
    ligand_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Rewrite the job index atomically, fsync once.

    The tmp-file swap means a crash mid-write leaves the previous index
    intact; one fsync is enough for the stage/terminal durability the
    recovery rules promise (TASK-07 §4.2).  A failed persist must never
    break the run itself — it degrades to a warning.

    ``ligand_rows`` is the full batch row list handed to the per-ligand
    results index (TASK-13 §4.7); None leaves a batch indexed at run level
    only — the payload's truncated slice must never masquerade as complete.
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
    # Terminal snapshots feed the results index (TASK-15 §4.2).  The hook
    # lives in this single write funnel so cancel and reap paths index too,
    # not just the normal completion events.  An index write failure above
    # does not veto it: the payload is still valid in memory.
    if payload.get("status") in results_db.TERMINAL_STATUSES:
        try:
            results_db.ingest_job_payload(payload, ligand_rows=ligand_rows)
        except Exception:
            log.warning("results ingest failed for %s", job_id, exc_info=True)


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
    slice stored in ``job.json``.  The column mapping itself lives in
    ``results_db`` next to the backfill that reads the same artifact, so
    the two parsers cannot drift (TASK-27 勘误 ⑩).
    """
    text = _read_job_text(job_id, BATCH_RESULTS_CSV_FILENAME)
    if not text:
        return None
    return results_db.parse_batch_results_csv(text)


def _state_from_payload(data: dict[str, Any], job_id: str) -> JobState:
    """Build a ``JobState`` from a persisted index, hydrating by convention.

    The large fields never ride in the JSON; screening rows and batch CSVs
    land here eagerly because the summary is meaningless without them, while
    log/poses are deferred to the first ``get_job()`` (TASK-28 P2-A,
    TASK-07 §4.2).
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
        is_screening=bool(data.get("isScreening")),
        is_site_screening=bool(data.get("isSiteScreening")),
        is_ensemble=bool(data.get("isEnsemble")),
        ensemble_results=list(data.get("ensembleResults") or []),
        best_receptor=data.get("bestReceptor"),
        total_ligands=int(data.get("totalLigands") or 0),
        completed_ligands=int(data.get("completedLigands") or 0),
        failed_ligands=int(data.get("failedLigands") or 0),
        label=str(data.get("label") or ""),
        params=dict(data.get("params") or {}),
    )

    if state.is_screening:
        # Rows live in jsonl; counters and best are re-derived from them,
        # because job.json only ever saw the last stage event before the
        # crash, while the append-only rows are complete (TASK-13 §4.2).
        _, done, failed, derived_best = screening_jsonl_progress(job_id)
        state.completed_ligands = done
        state.failed_ligands = failed
        if state.total_ligands > 0:
            state.progress = int((done + failed) / state.total_ligands * 100)
        if derived_best is not None:
            state.screening_best = derived_best
        else:
            # jsonl missing/unreadable (rows failed to flush): fall back to
            # whatever the last settle wrote, else None — never a fake zero.
            best = data.get("bestAffinity")
            state.screening_best = float(best) if isinstance(best, (int, float)) else None
    elif state.is_batch:
        from_csv = _read_batch_csv(job_id)
        # The CSV artifact exists only for truncated batches; otherwise the
        # index itself already holds every row.
        state.batch_results = from_csv if from_csv else list(data.get("batchResults") or [])
    # The large text fields (log, poses) are left empty here: a restored job
    # reads them on first get_job() instead (TASK-28 P2-A), so startup never
    # pays for files the session may never open.
    state.needs_hydration = True
    state.artifacts = (
        # Interrupted run: the on-disk set is all there ever will be.
        _collect_job_artifacts(job_id)
        if interrupted
        else [a for a in (data.get("artifacts") or []) if isinstance(a, dict)]
    )
    return state


def _hydrate_state(state: JobState) -> None:
    """Fill the deferred text fields of a restored job (TASK-28 P2-A).

    Mirrors what ``_state_from_payload`` used to read eagerly: the capped
    log ring plus, for a completed single run, the pose artifacts.  Called
    from ``get_job`` under the manager lock — the flag flip makes it a
    one-shot, and a second get_job never touches the disk again.
    """
    if not state.is_screening and not state.is_batch and state.status == "completed":
        state.poses_pdbqt = _read_job_text(state.job_id, "poses.pdbqt")
        state.poses_sdf = _read_job_text(state.job_id, POSES_SDF_FILENAME)
    state.log = _read_job_log(state.job_id)
    state.needs_hydration = False


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
        "pose_count", "error", "qed", "lipinski_violations",
    ])
    for r in batch_results:
        # csv renders None as an empty cell — the agreed null rule (§4.6).
        writer.writerow([
            r.get("ligandIndex", ""),
            r.get("label", ""),
            r.get("status", ""),
            r.get("bestAffinity", ""),
            r.get("nPoses", 0),
            r.get("error", ""),
            r.get("qed"),
            r.get("lipinskiViolations"),
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


def _screening_worker_entry(params: dict[str, Any], pipe: Any) -> None:
    """Entry point for a virtual screening child process."""
    from vinastudio.core.worker import screening_worker

    screening_worker(params, pipe)


def _ensemble_worker_entry(params: dict[str, Any], pipe: Any) -> None:
    from vinastudio.core.worker import ensemble_worker

    ensemble_worker(params, pipe)


def _site_screening_worker_entry(params: dict[str, Any], pipe: Any) -> None:
    """Entry point for a site-screen child process (S2)."""
    from vinastudio.core.worker import site_screening_worker

    site_screening_worker(params, pipe)


#: Module-level singleton shared across the application.
manager = JobManager()
