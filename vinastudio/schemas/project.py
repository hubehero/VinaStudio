"""Project file schema for .vinaproj files."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectBox(BaseModel):
    """Box configuration saved in a project file."""

    model_config = ConfigDict(extra="forbid")

    center: list[float]
    size: list[float]


class ProjectDockingConfig(BaseModel):
    """Docking configuration saved in a project file."""

    model_config = ConfigDict(extra="forbid")

    scoring: str = "vina"
    exhaustiveness: int = 8
    nPoses: int = 20
    energyRange: float = 3.0
    minRmsd: float = 1.0
    cpu: int = 0
    seed: int = 0
    noRefine: bool = False


class ProjectLigand(BaseModel):
    """A ligand entry saved in a project file."""

    model_config = ConfigDict(extra="forbid")

    label: str
    path: str | None = None
    pdbqtString: str | None = None


class ProjectReceptor(BaseModel):
    """Receptor configuration saved in a project file."""

    model_config = ConfigDict(extra="forbid")

    path: str
    flexPath: str | None = None


class ProjectFile(BaseModel):
    """Root model for a .vinaproj project file."""

    model_config = ConfigDict(extra="forbid")

    formatVersion: str = "1.0"
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now().isoformat())
    name: str = ""
    description: str = ""

    receptor: ProjectReceptor | None = None
    ligands: list[ProjectLigand] = Field(default_factory=list)
    box: ProjectBox | None = None
    docking: ProjectDockingConfig = Field(default_factory=ProjectDockingConfig)

    # Results metadata (not the actual results, just references)
    lastJobId: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
