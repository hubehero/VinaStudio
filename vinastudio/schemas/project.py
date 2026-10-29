"""Project file schema for .vinaproj files."""

from __future__ import annotations

from datetime import datetime

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
    maxEvals: int = 0
    verbosity: int = 1
    mapPaths: list[str] | None = None
    weights: list[float] | None = None


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


class ProjectResultRef(BaseModel):
    """A pointer to one job's artifacts under ``<workspace>/jobs/<id>/``.

    Format 1.1 (TASK-07): projects reference results instead of embedding
    them.  ``extra="ignore"`` because before 1.1 ``results`` was an untyped
    dict — older files may carry keys this model does not know, and a load
    must never fail over them.
    """

    model_config = ConfigDict(extra="ignore")

    jobId: str
    label: str = ""


class ProjectFile(BaseModel):
    """Root model for a .vinaproj project file."""

    model_config = ConfigDict(extra="forbid")

    formatVersion: str = "1.1"
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
    results: list[ProjectResultRef] = Field(default_factory=list)
