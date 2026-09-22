"""Workspace management endpoints.

These endpoints let the frontend:
- query the current workspace (GET /api/workspace)
- initialise a new workspace on first launch (POST /api/workspace/init)
- switch to a different workspace (POST /api/workspace/set)
- migrate the workspace to a new disk location (POST /api/workspace/migrate)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from vinastudio import config
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.workspace import (
    _SUBDIRS,
    init_workspace,
    is_workspace,
    load_config,
    migrate_workspace,
    save_config,
)
from vinastudio.schemas.workspace import (
    WorkspaceInfo,
    WorkspaceInitRequest,
    WorkspaceMigrateRequest,
    WorkspaceSetRequest,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level mutable state — the active workspace path for this session.
# Persisted under the application home so restarts remember it.
# ---------------------------------------------------------------------------


def _state_file() -> Path:
    """Where the active workspace is remembered; honours ``VINASTUDIO_HOME``."""
    return config.app_home() / "workspace.json"


def _load_active_path() -> Path | None:
    """Return the persisted active-workspace path, or ``None``."""
    state_file = _state_file()
    if not state_file.is_file():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        p = Path(data["path"])
        if is_workspace(p):
            return p
        log.warning("recorded workspace is not a VinaStudio workspace: %s", p)
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        # Silently returning None would look like a first launch and send the
        # user back to the wizard with no hint about what happened.
        log.warning("could not read %s: %s", state_file, exc)
    return None


def _save_active_path(path: Path) -> None:
    """Persist the active-workspace path across restarts."""
    state_file = _state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # Written through a temporary file: a half-written state file is unreadable
    # and would present as "no workspace configured".
    tmp = state_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"path": str(path)}), encoding="utf-8")
    os.replace(tmp, state_file)


# On import, resolve the active workspace (may be ``None``).
_active_workspace: Path | None = _load_active_path()


def get_active_workspace() -> Path | None:
    """Public accessor used by other routers that need the workspace root."""
    return _active_workspace


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=WorkspaceInfo)
def get_workspace() -> WorkspaceInfo:
    """Return information about the currently active workspace.

    Returns ``isValid=false`` if no workspace has been configured yet
    (first launch).
    """
    if _active_workspace is None:
        return WorkspaceInfo(
            path="",
            name="",
            version=0,
            createdAt="",
            isValid=False,
            subdirectories={},
        )

    config = load_config(_active_workspace)
    return WorkspaceInfo(
        path=str(_active_workspace),
        name=config.name,
        version=config.version,
        createdAt=config.created_at,
        isValid=True,
        subdirectories={name: str(_active_workspace / name) for name in _SUBDIRS},
    )


@router.post("/init", response_model=WorkspaceInfo)
def init_workspace_endpoint(req: WorkspaceInitRequest) -> WorkspaceInfo:
    """Create a brand-new workspace directory tree.

    Called by the first-launch wizard.
    """
    global _active_workspace

    # Path("") resolves to the process CWD: initialising that by accident used
    # to scatter a workspace over whatever directory the app was launched from.
    if not req.path.strip():
        raise InvalidInputError("workspace path is required")
    path = Path(req.path).expanduser().resolve()
    config = init_workspace(path, name=req.name)
    _active_workspace = path
    _save_active_path(path)

    return WorkspaceInfo(
        path=str(path),
        name=config.name,
        version=config.version,
        createdAt=config.created_at,
        isValid=True,
        subdirectories={name: str(path / name) for name in _SUBDIRS},
    )


@router.post("/set", response_model=WorkspaceInfo)
def set_workspace_endpoint(req: WorkspaceSetRequest) -> WorkspaceInfo:
    """Switch to an existing workspace directory."""
    global _active_workspace

    if not req.path.strip():
        raise InvalidInputError("workspace path is required")
    path = Path(req.path).expanduser().resolve()
    if not is_workspace(path):
        # Auto-initialise if the directory is empty.
        if path.is_dir() and not any(path.iterdir()):
            config = init_workspace(path)
        else:
            raise InvalidInputError(
                f"{path} is not a VinaStudio workspace. "
                "Use POST /api/workspace/init to create one."
            )
    else:
        config = load_config(path)

    _active_workspace = path
    _save_active_path(path)

    return WorkspaceInfo(
        path=str(path),
        name=config.name,
        version=config.version,
        createdAt=config.created_at,
        isValid=True,
        subdirectories={name: str(path / name) for name in _SUBDIRS},
    )


@router.post("/migrate", response_model=WorkspaceInfo)
def migrate_workspace_endpoint(req: WorkspaceMigrateRequest) -> WorkspaceInfo:
    """Copy the workspace to a new location and switch to it."""
    global _active_workspace

    if _active_workspace is None:
        raise InvalidInputError("no active workspace to migrate")

    if not req.target_path.strip():
        raise InvalidInputError("target path is required")
    target = Path(req.target_path).expanduser().resolve()
    config = migrate_workspace(_active_workspace, target)
    _active_workspace = target
    _save_active_path(target)

    return WorkspaceInfo(
        path=str(target),
        name=config.name,
        version=config.version,
        createdAt=config.created_at,
        isValid=True,
        subdirectories={name: str(target / name) for name in _SUBDIRS},
    )


@router.put("/name", response_model=WorkspaceInfo)
def rename_workspace(name: str = "") -> WorkspaceInfo:
    """Update the human-readable workspace name."""
    global _active_workspace

    if _active_workspace is None:
        raise InvalidInputError("no active workspace")
    # An empty name used to silently keep the old one, so the rename button
    # did nothing with no hint why.
    if not name.strip():
        raise InvalidInputError("workspace name is required")

    config = load_config(_active_workspace)
    config.name = name.strip()
    save_config(_active_workspace, config)

    return WorkspaceInfo(
        path=str(_active_workspace),
        name=config.name,
        version=config.version,
        createdAt=config.created_at,
        isValid=True,
        subdirectories={s: str(_active_workspace / s) for s in _SUBDIRS},
    )
