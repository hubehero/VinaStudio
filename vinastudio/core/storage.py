"""Read-only job-storage accounting and explicitly requested terminal cleanup.

The workspace history is durable user data.  Nothing in this module deletes on
startup or during a diagnostic; deletion is a separate, explicit operation and
only accepts an indexed **terminal** job.  Preparation directories without a
``job.json`` are never candidates.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from vinastudio.core.paths import JOB_STATE_FILENAME

TERMINAL = frozenset({"completed", "failed", "cancelled"})
# Production ids are 12-character lowercase hex; the wider safe alphabet keeps
# never joined to a filesystem path directly; it must name one of these
# already-enumerated directories.
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _directory_size(directory: Path) -> tuple[int, int]:
    total = 0
    files = 0
    try:
        for item in directory.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
                files += 1
    except OSError:
        pass
    return total, files


def _read_index(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def summarize_jobs(root: Path) -> dict[str, Any]:
    """Return byte/file counts for every indexed job under *root*.

    Unindexed preparation directories are intentionally excluded: they may be
    inputs still referenced by the current pipeline and are not history items.
    """
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        children = []
    for child in children:
        if not child.is_dir():
            continue
        index = child / JOB_STATE_FILENAME
        if not index.is_file():
            continue
        payload = _read_index(index)
        if payload is None:
            status = "unreadable"
            label = ""
            created = 0.0
            deletable = False
        else:
            status = str(payload.get("status") or "unknown")
            label = str(payload.get("label") or "")
            created = float(payload.get("createdAt") or 0.0)
            deletable = status in TERMINAL
        bytes_size, files = _directory_size(child)
        entries.append(
            {
                "jobId": child.name,
                "label": label,
                "status": status,
                "createdAt": created,
                "bytes": bytes_size,
                "files": files,
                "deletable": deletable,
            }
        )
    entries.sort(key=lambda row: (row["createdAt"], row["jobId"]), reverse=True)
    total = sum(row["bytes"] for row in entries)
    deletable = sum(row["bytes"] for row in entries if row["deletable"])
    return {
        "count": len(entries),
        "totalBytes": total,
        "deletableBytes": deletable,
        "entries": entries,
    }


def _find_job_directory(root: Path, job_id: str) -> Path:
    """Find an existing child by exact id without using it as a path segment.

    Enumeration keeps the filesystem expression independent of request data.
    The regex is a second guard for malformed/legacy ids; both failures are
    reported as invalid rather than as a missing job.
    """
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError(f"job id escapes the jobs root: {job_id}")
    try:
        for child in root.resolve().iterdir():
            if child.name == job_id and child.is_dir():
                return child
    except OSError as exc:
        raise FileNotFoundError(job_id) from exc
    raise FileNotFoundError(job_id)


def delete_terminal_job(root: Path, job_id: str) -> dict[str, Any]:
    """Delete one indexed terminal job; return its id/bytes.

    Raises ``FileNotFoundError`` for no index and ``ValueError`` for a
    non-terminal, malformed or unreadable job.  The directory is selected by
    enumerating the jobs root, never by joining request data to a path.
    """
    directory = _find_job_directory(root, job_id)
    index = directory / JOB_STATE_FILENAME
    payload = _read_index(index)
    if payload is None:
        raise ValueError("job index is missing or unreadable")
    status = str(payload.get("status") or "")
    if status not in TERMINAL:
        raise ValueError(f"job is {status or 'unknown'}, not terminal")
    bytes_size, _ = _directory_size(directory)
    shutil.rmtree(directory)
    return {"jobId": directory.name, "bytes": bytes_size}
