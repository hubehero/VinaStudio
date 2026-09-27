"""Molecule manifest schema for persistent storage.

The manifest lives at ``<workspace>/molecules.json`` and captures the full
molecule list with all metadata.  It is separate from ``.vinaproj`` files
(which capture docking workflow state) because a workspace can serve
multiple projects, each referencing subsets of the same molecules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MoleculeEntry(BaseModel):
    """Persistent representation of a single molecule."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    path: str
    size: int = 0

    # Type detection
    detectedType: str = "unknown"
    """'receptor' | 'ligand' | 'unknown'"""
    detectionConfidence: float = 0.0
    detectionSource: str = "extension"
    """'extension' | 'content' | 'user'"""
    detectionReason: str | None = None
    assignedType: str | None = None
    """User override for detectedType."""

    # Lifecycle
    status: str = "uploaded"
    """'uploaded' | 'inspecting' | 'inspected' | 'preparing' | 'prepared' | 'error'"""

    # Cached inspection/preparation results (opaque dicts)
    preview: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    pdbqt: str | None = None
    error: dict[str, Any] | None = None

    # Preparation options
    receptorOptions: dict[str, Any] = Field(default_factory=dict)
    ligandOptions: dict[str, Any] = Field(default_factory=dict)

    # Grouping (library downloads)
    groupId: str | None = None
    groupName: str | None = None

    # User metadata
    aliases: list[str] = Field(default_factory=list)
    """User-assigned aliases (e.g. Chinese names)."""
    category: str | None = None
    """User-assigned category (e.g. '激酶', '蛋白酶', '对照组')."""

    # Staleness detection
    mtime: float | None = None
    """File modification time at last inspection."""

    # Timestamps
    createdAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class MoleculeManifest(BaseModel):
    """Root model for the workspace-level molecule manifest."""

    model_config = ConfigDict(extra="forbid")

    formatVersion: str = "1.0"
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    molecules: list[MoleculeEntry] = Field(default_factory=list)
