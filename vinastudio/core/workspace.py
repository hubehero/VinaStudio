"""Workspace configuration and directory management.

VinaStudio stores all project data under a single user-chosen workspace
directory.  On first launch the user picks a root folder; every subsequent
session reads the configuration from ``<workspace>/.vinastudio.json``.

Directory layout inside the workspace::

    <workspace>/
    ├── .vinastudio.json        # workspace metadata (created once)
    ├── projects/               # .vinaproj files
    ├── receptors/              # uploaded receptor PDB/PDBQT/CIF files
    ├── ligands/                # uploaded ligand SDF/MOL/MOL2 files
    ├── jobs/                   # docking job outputs (per-job subdirs)
    └── exports/                # exported CSV / SDF results
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vinastudio.core.errors import InvalidInputError

WORKSPACE_VERSION = 1
_CONFIG_FILENAME = ".vinastudio.json"

# Subdirectories created inside every workspace.
_SUBDIRS = ("projects", "receptors", "ligands", "jobs", "exports")


# ── workspace configuration model ────────────────────────────────────────────


class WorkspaceConfig:
    """In-memory representation of ``.vinastudio.json``."""

    def __init__(
        self,
        *,
        version: int = WORKSPACE_VERSION,
        created_at: str | None = None,
        name: str = "VinaStudio Workspace",
        **_extra: Any,
    ) -> None:
        self.version = version
        self.created_at = created_at or datetime.now(UTC).isoformat()
        self.name = name

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "createdAt": self.created_at,
            "name": self.name,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ── core helpers ─────────────────────────────────────────────────────────────


def _config_path(workspace: Path) -> Path:
    return workspace / _CONFIG_FILENAME


def load_config(workspace: Path) -> WorkspaceConfig:
    """Read the workspace config file, raising if it does not exist."""
    path = _config_path(workspace)
    if not path.is_file():
        raise InvalidInputError(
            f"{workspace} is not a valid VinaStudio workspace "
            f"(missing {_CONFIG_FILENAME})"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise InvalidInputError(
            f"cannot read workspace config: {exc}"
        ) from exc
    return WorkspaceConfig(**data)


def save_config(workspace: Path, config: WorkspaceConfig) -> None:
    """Write (or overwrite) the workspace config file."""
    workspace.mkdir(parents=True, exist_ok=True)
    _config_path(workspace).write_text(config.to_json(), encoding="utf-8")


def init_workspace(workspace: Path, *, name: str = "VinaStudio Workspace") -> WorkspaceConfig:
    """Create the workspace directory tree and config file.

    Returns the freshly created config.  Raises if the directory already
    contains a config (call :func:`load_config` instead).
    """
    if _config_path(workspace).is_file():
        raise InvalidInputError(f"{workspace} is already initialised as a workspace")

    workspace.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (workspace / sub).mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(name=name)
    save_config(workspace, config)
    return config


def ensure_workspace(workspace: Path) -> WorkspaceConfig:
    """Load an existing workspace or create one with defaults."""
    if _config_path(workspace).is_file():
        return load_config(workspace)
    return init_workspace(workspace)


def is_workspace(workspace: Path) -> bool:
    """Return ``True`` if *workspace* contains a valid config file."""
    return _config_path(workspace).is_file()


# ── subdirectory accessors ───────────────────────────────────────────────────


def _subdir(workspace: Path, name: str) -> Path:
    """Return (and create if needed) a workspace subdirectory."""
    if name not in _SUBDIRS:
        raise ValueError(f"unknown workspace subdirectory {name!r}")
    d = workspace / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir(workspace: Path) -> Path:
    return _subdir(workspace, "projects")


def receptors_dir(workspace: Path) -> Path:
    return _subdir(workspace, "receptors")


def ligands_dir(workspace: Path) -> Path:
    return _subdir(workspace, "ligands")


def jobs_dir(workspace: Path) -> Path:
    return _subdir(workspace, "jobs")


def exports_dir(workspace: Path) -> Path:
    return _subdir(workspace, "exports")


# ── migration ────────────────────────────────────────────────────────────────


def migrate_workspace(source: Path, target: Path) -> WorkspaceConfig:
    """Copy the entire workspace from *source* to *target*.

    The target must not already be an initialised workspace.  After a
    successful copy the source config is left untouched so the user can
    verify the migration before deleting the old directory.
    """
    if not source.is_dir():
        raise InvalidInputError(f"source directory does not exist: {source}")
    if not is_workspace(source):
        raise InvalidInputError(f"source is not a VinaStudio workspace: {source}")
    if target.exists() and any(target.iterdir()):
        raise InvalidInputError(
            f"target directory is not empty: {target}. "
            "Choose an empty directory or a non-existent path."
        )

    source_root = source.resolve()
    target_root = target.resolve()
    if target_root == source_root or target_root.is_relative_to(source_root):
        # Otherwise the copy walks its own destination.
        raise InvalidInputError(
            f"target directory must not be inside the source: {target}"
        )

    # Snapshot the source before creating the target for the same reason.
    items = list(source.iterdir())

    target.mkdir(parents=True, exist_ok=True)

    # Copy everything, then reload config from the new location.
    for item in items:
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    return load_config(target)
