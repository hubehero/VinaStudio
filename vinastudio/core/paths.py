"""Per-run working directories for preparation and docking artefacts.

Every preparation writes into its own directory under the active workspace's
``jobs/`` subdirectory.  That keeps ``write_poses``-style "refuse to
overwrite" behaviour harmless, makes a run reproducible after the fact, and
gives the interface a stable place to fetch large artefacts (a receptor PDB is
hundreds of kilobytes, which has no business travelling inside a JSON response).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_workspace_provider: Callable[[], Path | None] | None = None


def set_workspace_provider(provider: Callable[[], Path | None] | None) -> None:
    """Let the server inject the active workspace without making core import it."""
    global _workspace_provider
    _workspace_provider = provider

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def workspace_root() -> Path:
    """Root of all run directories — uses the active workspace jobs/ subdir."""
    from vinastudio.config import app_home

    ws = _workspace_provider() if _workspace_provider is not None else None
    # The fallback must go through app_home(), which honours VINASTUDIO_HOME.
    # Hard-coding ~/.vinastudio here sent test runs (that redirect the variable
    # for isolation) into the user's real home directory.
    root = ws / "jobs" if ws is not None else app_home() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def slugify(text: str, *, fallback: str = "run", limit: int = 40) -> str:
    """Turn a filename into a filesystem-safe fragment."""
    slug = _SLUG_STRIP.sub("-", Path(text).stem.lower()).strip("-")
    return slug[:limit] or fallback


#: Per-job persistence filenames inside ``<workspace>/jobs/<job_id>/``.
#: ``job.json`` is the crash-safe index the job manager rewrites on stage
#: changes and terminal states; the log lives beside it because large text
#: must never travel inside the JSON (HANDBOOK §4.6).
JOB_STATE_FILENAME = "job.json"
JOB_LOG_FILENAME = "job.log"
POSES_SDF_FILENAME = "poses.sdf"
BATCH_RESULTS_CSV_FILENAME = "batch_results.csv"
#: Append-only per-molecule rows of a screening run (TASK-13 §4.2): the
#: writer (job_manager) and the resume/ranking/ingest readers share one
#: spelling of the name, so it lives with the other job filenames.
SCREENING_JSONL_FILENAME = "screening.jsonl"
#: Per-candidate rows of a site screen (S2): one append-only line per box.
SITES_JSONL_FILENAME = "sites.jsonl"

#: Analysis-cache convention (TASK-07 §4.7) — format agreed, implementation
#: arrives with each analysis task: a JSON array of entries shaped
#: ``{"kind": str, "paramsHash": str, "payload": any}``.  An entry whose
#: ``paramsHash`` no longer matches the request is stale and is recomputed
#: rather than trusted.
ANALYSIS_CACHE_FILENAME = "analysis.json"


def job_dir(job_id: str) -> Path:
    """Directory holding one docking job's artifacts and index file."""
    return workspace_root() / job_id


def job_state_path(job_id: str) -> Path:
    """The per-job index file the job manager persists and restores from."""
    return job_dir(job_id) / JOB_STATE_FILENAME


def job_log_path(job_id: str) -> Path:
    """Append-only log file for a job, replayed after a restart."""
    return job_dir(job_id) / JOB_LOG_FILENAME


@dataclass(slots=True)
class Workspace:
    """A directory that belongs to one preparation or docking run."""

    path: Path
    run_id: str

    def file(self, name: str) -> Path:
        return self.path / name

    def write(self, name: str, content: str) -> Path:
        target = self.file(name)
        target.write_text(content, encoding="utf-8")
        return target

    def relative(self, target: Path) -> str:
        """Path relative to the workspace root, for building artefact URLs."""
        return target.relative_to(workspace_root()).as_posix()


def file_reuse_key(path: str | Path, *, extra: object = None) -> str:
    """Stable key for a source file plus its options.

    mtime and size change when the user edits the file; the resolved path keeps
    two different files with the same stem apart.
    """
    target = Path(path)
    try:
        stat = target.stat()
        signature = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        signature = "missing"
    return f"{target.resolve()}:{signature}:{extra!r}"


def create_workspace(
    prefix: str,
    *,
    stamp: str | None = None,
    reuse_key: str | None = None,
) -> Workspace:
    """Create a run directory, or reuse one for the same stable key.

    Preparation and rendering directories are content-addressed: repeating the
    same source/options pair reuses its directory instead of leaving another
    orphan under ``jobs/``. Docking jobs never pass ``reuse_key`` and keep the
    unique timestamped directory they need.
    """
    if reuse_key is not None:
        digest = hashlib.sha256(reuse_key.encode("utf-8")).hexdigest()[:12]
        run_id = f"{slugify(prefix)}-{digest}"
        path = workspace_root() / run_id
        path.mkdir(parents=True, exist_ok=True)
        # Overwriting an existing file does not update the directory mtime;
        # without this touch the 30-day cleanup could reclaim a dir in active use.
        os.utime(path, None)
        return Workspace(path=path, run_id=path.name)

    run_id = f"{stamp or time.strftime('%Y%m%d-%H%M%S')}-{slugify(prefix)}"
    root = workspace_root()
    suffix = 0
    for _ in range(100):
        path = root / (run_id if suffix == 0 else f"{run_id}-{suffix}")
        try:
            path.mkdir(parents=True)
        except FileExistsError:
            # A pre-existing name or a TOCTOU race with another process; try
            # the next suffix instead of failing the request.
            suffix += 1
            continue
        return Workspace(path=path, run_id=path.name)
    raise RuntimeError(f"could not allocate a workspace directory for {prefix!r}")


def cleanup_orphan_workspaces(
    *,
    older_than_days: int = 30,
    root: Path | None = None,
    protected: set[Path] | None = None,
) -> int:
    """Remove old preparation/render directories that never became jobs.

    A directory with ``job.json`` is a docking job and is never touched, even
    if it is old. ``protected`` holds prepared directories still referenced by
    persisted state (manifest, projects, catalog); deleting one leaves the
    interface with a URL that can only 404.
    """
    base = root or workspace_root()
    cutoff = time.time() - older_than_days * 86400
    protected = {path.resolve() for path in (protected or ())}
    try:
        entries = list(base.iterdir())
    except OSError:
        return 0
    removed = 0
    for entry in entries:
        if not entry.is_dir() or (entry / JOB_STATE_FILENAME).exists():
            continue
        try:
            if entry.resolve() in protected:
                continue
            if entry.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(entry)
        except OSError:
            log.warning("could not remove orphan workspace %s", entry, exc_info=True)
        else:
            removed += 1
    return removed


def resolve_within(root: Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` inside ``root``, refusing anything that escapes.

    An absolute ``candidate`` is accepted only when it already points inside
    ``root``; a relative one is joined to ``root`` first. Either way a ``..``
    segment can never leave ``root``, which is what callers rely on when the
    segment arrives from a URL or a request body.
    """
    base = Path(root).resolve()
    resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"path escapes {base}: {candidate}")
    return resolved


def resolve_artifact(relative: str) -> Path:
    """Resolve a path inside the workspace root, refusing escapes."""
    return resolve_within(workspace_root(), relative)
