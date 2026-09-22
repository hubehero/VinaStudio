"""Project endpoints: save, load, list projects.

All project files are stored under the active workspace's ``projects/``
subdirectory.  If no workspace has been configured yet the endpoints fall
back to the legacy ``~/.vinastudio/projects`` location so existing users
are not broken.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import resolve_within
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

    # Sanitize filename
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

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(), f, indent=2, ensure_ascii=False)

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

    try:
        project = ProjectFile(**project_data)
        project.updatedAt = datetime.now().isoformat()

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(), f, indent=2, ensure_ascii=False)

        return {
            "path": str(filepath),
            "filename": filepath.name,
            "status": "saved",
        }
    except Exception as e:
        log.exception("Failed to save project")
        raise InvalidInputError(f"Failed to save project: {e}") from None


@router.post("/load")
def load_project(request: dict[str, Any]) -> dict[str, Any]:
    """Load a project from a .vinaproj file."""
    filepath_str = request.get("path", "")

    if not filepath_str:
        raise InvalidInputError("path is required")

    filepath = Path(filepath_str)
    if not filepath.exists():
        raise InvalidInputError(f"project file not found: {filepath_str}")

    if filepath.suffix != ".vinaproj":
        raise InvalidInputError(f"not a .vinaproj file: {filepath_str}")

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        project = ProjectFile(**data)
        return {
            "path": str(filepath),
            "project": project.model_dump(),
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

    if filepath.suffix != ".vinaproj":
        raise InvalidInputError(f"not a .vinaproj file: {filename}")

    filepath.unlink()
    return {"status": "deleted", "filename": filename}
