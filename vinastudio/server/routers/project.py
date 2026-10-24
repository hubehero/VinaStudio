"""Project endpoints: save, load, list projects.

All project files are stored under the active workspace's ``projects/``
subdirectory.  If no workspace has been configured yet the endpoints fall
back to the legacy ``~/.vinastudio/projects`` location so existing users
are not broken.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import JOB_STATE_FILENAME, resolve_within, workspace_root
from vinastudio.schemas.project import ProjectFile

log = logging.getLogger(__name__)

router = APIRouter(prefix="/project", tags=["project"])

_LEGACY_DIR = Path.home() / ".vinastudio" / "projects"


def _get_projects_dir() -> Path:
    """Resolve the projects directory from the active workspace."""
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    d = ws / "projects" if ws is not None else _LEGACY_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_project(filepath: Path, project: ProjectFile) -> None:
    """Write a project atomically, so a crash cannot truncate an existing file.

    ``NamedTemporaryFile`` lives in the destination directory, which keeps the
    final ``os.replace`` on the same filesystem (the only way it is atomic).
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(project.model_dump(), indent=2, ensure_ascii=False)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{filepath.name}.", suffix=".tmp", dir=filepath.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, filepath)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


# ── endpoints ────────────────────────────────────────────────────────────────


@router.post("/save")
def save_project(request: dict[str, Any]) -> dict[str, str]:
    """Save a project to a .vinaproj file.

    Expects JSON body with:
    - filename: suggested filename (without extension)
    - project: ProjectFile data
    """
    filename = request.get("filename", "untitled")
    project_data = request.get("project", {})

    # Sanitize filename. A caller may send the extension even though the
    # endpoint adds it; strip it before sanitising so the dot is not first
    # rewritten to an underscore.
    if filename.lower().endswith(".vinaproj"):
        filename = filename[:-len(".vinaproj")]
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in filename)
    safe_name = safe_name.strip()[:100] or "untitled"

    projects_dir = _get_projects_dir()
    filepath = projects_dir / f"{safe_name}.vinaproj"

    # Ensure unique filename
    counter = 1
    while filepath.exists():
        filepath = projects_dir / f"{safe_name}_{counter}.vinaproj"
        counter += 1

    try:
        project = ProjectFile(**project_data)
        project.updatedAt = datetime.now().isoformat()
        # A direct API caller may omit the display name; the filename is the
        # least surprising fallback.
        project.name = project.name or safe_name
        # Saving writes the current format, whatever the client sent.
        project.formatVersion = "1.1"
        _write_project(filepath, project)

        return {
            "path": str(filepath),
            "filename": filepath.name,
            "status": "saved",
        }
    except Exception as e:
        log.exception("Failed to save project")
        raise InvalidInputError(f"Failed to save project: {e}") from None


@router.post("/save-as")
def save_project_as(request: dict[str, Any]) -> dict[str, str]:
    """Save a project to a specific path."""
    filepath_str = request.get("path", "")
    project_data = request.get("project", {})

    if not filepath_str:
        raise InvalidInputError("path is required")

    filepath = Path(filepath_str)
    if not filepath.suffix:
        filepath = filepath.with_suffix(".vinaproj")
    if filepath.suffix.lower() != ".vinaproj":
        raise InvalidInputError("project path must end with .vinaproj")
    if filepath.is_dir():
        raise InvalidInputError(f"project path is a directory: {filepath}")

    try:
        project = ProjectFile(**project_data)
        project.updatedAt = datetime.now().isoformat()
        project.name = project.name or filepath.stem
        project.formatVersion = "1.1"
        _write_project(filepath, project)

        return {
            "path": str(filepath),
            "filename": filepath.name,
            "status": "saved",
        }
    except Exception as e:
        log.exception("Failed to save project")
        raise InvalidInputError(f"Failed to save project: {e}") from None


def _job_index_exists(job_id: str) -> bool:
    """True when a referenced job still has its index in this workspace.

    The id travels in a file the user can edit, so it is resolved against the
    workspace root first — an escaping id counts as missing, never as a path
    to probe outside.
    """
    try:
        directory = resolve_within(workspace_root(), job_id)
    except ValueError:
        return False
    return (directory / JOB_STATE_FILENAME).is_file()


@router.post("/load")
def load_project(request: dict[str, Any]) -> dict[str, Any]:
    """Load a project from a .vinaproj file.

    Result references whose job artifacts are gone come back as warnings:
    the project itself still loads (TASK-07 §4.5 — 提示不报错).
    """
    filepath_str = request.get("path", "")

    if not filepath_str:
        raise InvalidInputError("path is required")

    filepath = Path(filepath_str)
    if not filepath.exists():
        raise InvalidInputError(f"project file not found: {filepath_str}")

    if filepath.suffix.lower() != ".vinaproj":
        raise InvalidInputError(f"not a .vinaproj file: {filepath_str}")

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        project = ProjectFile(**data)
        warnings = [
            f"result job {ref.jobId} no longer exists in this workspace"
            for ref in project.results
            if not _job_index_exists(ref.jobId)
        ]
        return {
            "path": str(filepath),
            "project": project.model_dump(),
            "warnings": warnings,
        }
    except json.JSONDecodeError as e:
        raise InvalidInputError(f"invalid JSON in project file: {e}") from None
    except Exception as e:
        log.exception("Failed to load project")
        raise InvalidInputError(f"Failed to load project: {e}") from None


@router.get("/list")
def list_projects() -> list[dict[str, Any]]:
    """List all saved projects."""
    projects_dir = _get_projects_dir()
    projects = []

    for filepath in sorted(projects_dir.glob("*.vinaproj"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            projects.append({
                "path": str(filepath),
                "filename": filepath.name,
                "name": data.get("name", filepath.stem),
                "createdAt": data.get("createdAt", ""),
                "updatedAt": data.get("updatedAt", ""),
                "description": data.get("description", ""),
            })
        except (json.JSONDecodeError, OSError):
            # Skip invalid project files
            continue

    return projects


@router.delete("/{filename:path}")
def delete_project(filename: str) -> dict[str, str]:
    """Delete a project file."""
    projects_dir = _get_projects_dir()

    # The route captures path separators, so a `..` segment would otherwise
    # delete any `.vinaproj` file the process can reach.
    try:
        filepath = resolve_within(projects_dir, filename)
    except ValueError as exc:
        raise InvalidInputError(f"invalid project name: {filename}") from exc

    if not filepath.exists():
        raise InvalidInputError(f"project not found: {filename}")

    if filepath.suffix.lower() != ".vinaproj":
        raise InvalidInputError(f"not a .vinaproj file: {filename}")

    filepath.unlink()
    return {"status": "deleted", "filename": filename}
