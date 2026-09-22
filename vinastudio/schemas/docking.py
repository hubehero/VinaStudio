"""Request and response models for the docking endpoints.

The HTTP contract is deliberately separate from the ``core`` dataclasses so the
API surface can evolve independently of internal refactoring.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.config import DEFAULTS, SCORING_WEIGHT_COUNT, ScoringFunction


class DockingRequest(BaseModel):
    """Body of ``POST /api/docking/start``."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str = Field(description="Path to prepared receptor PDBQT.")
    flexReceptorPath: str | None = Field(
        default=None,
        description="Path to flexible sidechain PDBQT (optional).",
    )
    ligandPath: str | None = Field(
        default=None,
        description="Path to prepared ligand PDBQT. Either ligandPath or ligandPdbqtString must be provided.",
    )
    ligandPdbqtString: str | None = Field(
        default=None,
        description="PDBQT content for the ligand (in-memory, no filesystem round-trip).",
    )
    center: tuple[float, float, float] = Field(description="Box centre (x, y, z).")
    size: tuple[float, float, float] = Field(description="Box edge lengths (x, y, z).")
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = Field(default=8, ge=1, le=512)
    nPoses: int = Field(default=20, ge=1, le=100)
    energyRange: float = Field(default=3.0, gt=0)
    minRmsd: float = Field(default=1.0, ge=0)
    maxEvals: int = Field(default=0, ge=0)
    cpu: int = Field(default=0, ge=0)
    seed: int = Field(default=0, ge=0)
    noRefine: bool = False
    verbosity: int = Field(default=1, ge=0, le=2)
    spacing: float = Field(default=0.375, gt=0)
    forceEvenVoxels: bool = False
    weights: list[float] | None = Field(
        default=None,
        description="Custom scoring weights. None means use Vina defaults.",
    )
    mapPaths: list[str] | None = Field(
        default=None,
        description="AutoGrid4 map prefix (required for ad4 scoring).",
    )


class PoseInfo(BaseModel):
    """One docking pose."""

    index: int
    affinity: float
    rmsdLower: float
    rmsdUpper: float


class DockingJobCreated(BaseModel):
    """Response when a job is accepted."""

    jobId: str
    status: Literal["queued"]


class DockingJobStatus(BaseModel):
    """Current state of a docking job."""

    jobId: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int = Field(ge=0, le=100, description="Percentage 0-100.")
    stage: str | None = None
    log: list[str] = Field(default_factory=list)
    error: str | None = None
    elapsedMs: int | None = None


class DockingJobResult(BaseModel):
    """Completed job with poses and energy decomposition."""

    jobId: str
    status: Literal["completed"]
    poses: list[PoseInfo]
    bestAffinity: float
    posesPdbqt: str
    posesSdf: str
    nPoses: int
    scoring: ScoringFunction
    elapsedMs: int
    artifacts: list[dict] = Field(default_factory=list)


class DockingJobSummary(BaseModel):
    """Compact representation for the jobs list."""

    jobId: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int
    stage: str | None = None
    scoring: ScoringFunction
    elapsedMs: int | None = None


class DockingDefaultsResponse(BaseModel):
    """The UI fetches these to pre-fill the form.

    Every value is read from ``config.DEFAULTS``, so the published defaults are
    the ones the pipeline itself would use rather than a second copy of them.
    """

    scoring: ScoringFunction = DEFAULTS.scoring
    exhaustiveness: int = DEFAULTS.exhaustiveness
    nPoses: int = DEFAULTS.n_poses
    energyRange: float = DEFAULTS.energy_range
    minRmsd: float = DEFAULTS.min_rmsd
    maxEvals: int = DEFAULTS.max_evals
    cpu: int = DEFAULTS.cpu
    seed: int = DEFAULTS.seed
    noRefine: bool = DEFAULTS.no_refine
    verbosity: int = DEFAULTS.verbosity
    weightCounts: dict[str, int] = Field(default_factory=lambda: dict(SCORING_WEIGHT_COUNT))


class ScoreRequest(BaseModel):
    """Body of ``POST /api/docking/score``."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    flexReceptorPath: str | None = None
    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    scoring: ScoringFunction = "vina"
    spacing: float = 0.375
    forceEvenVoxels: bool = False
    unboundEnergy: float | None = None


class ScoreResponse(BaseModel):
    """Energy decomposition from a single-point score."""

    total: float
    inter: float
    intra: float
    torsions: float
    intra_best: float


class OptimizeRequest(BaseModel):
    """Body of ``POST /api/docking/optimize``."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    flexReceptorPath: str | None = None
    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    scoring: ScoringFunction = "vina"
    spacing: float = 0.375
    forceEvenVoxels: bool = False
    maxSteps: int = 0


class OptimizeResponse(BaseModel):
    """Result of local optimisation."""

    energy: float
    ligandPdbqt: str


class RandomizeRequest(BaseModel):
    """Body of ``POST /api/docking/randomize``.

    The receptor and the box are part of the contract because Vina's
    ``randomize`` needs the affinity maps: it generates ``maxSteps`` candidate
    conformers and keeps the lowest-energy one, so there is nothing to rank
    without the grid (``Cannot do ligand randomization. Affinity maps were not
    initialized.``).  This mirrors OptimizeRequest by library requirement, not
    by copy-paste.
    """

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    flexReceptorPath: str | None = None
    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    scoring: ScoringFunction = "vina"
    spacing: float = 0.375
    forceEvenVoxels: bool = False
    maxSteps: int = 10000
    #: Vina RNG seed; 0 lets Vina seed itself.  Set it to replay a randomisation.
    seed: int = Field(default=0, ge=0)


class RandomizeResponse(BaseModel):
    """Result of conformation randomisation."""

    ligandPdbqt: str


class ExportPoseRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{job_id}/export-pose``."""

    model_config = ConfigDict(extra="forbid")

    poseIndex: int = Field(ge=1, description="1-based pose index.")


class ExportPoseResponse(BaseModel):
    """A single exported pose."""

    poseIndex: int
    affinity: float
    pdbqt: str
    sdf: str


class VinaInfoResponse(BaseModel):
    """Vina library metadata."""

    version: str
    supportedScoringFunctions: list[str]
    cpuCount: int
    maxCPUs: int


class CitationResponse(BaseModel):
    """Citation text for the scoring function."""

    function: str
    citation: str


class BatchLigandItem(BaseModel):
    """A single ligand in a batch docking request."""

    model_config = ConfigDict(extra="forbid")

    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    label: str = ""
    """Optional label to distinguish results."""


class BatchDockingRequest(BaseModel):
    """Body of ``POST /api/docking/batch``.

    Shares a single receptor + box configuration across all ligands.
    """

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    flexReceptorPath: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    ligands: list[BatchLigandItem]
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = 8
    nPoses: int = 20
    energyRange: float = 3.0
    minRmsd: float = 1.0
    cpu: int = 0
    seed: int = 0
    noRefine: bool = False


class BatchLigandResult(BaseModel):
    """Result for a single ligand in a batch."""

    ligandIndex: int
    label: str
    status: str
    pdbqt: str = ""
    energies: list[PoseInfo] = Field(default_factory=list)
    bestAffinity: float | None = None
    nPoses: int = 0
    elapsedMs: int | None = None
    outDir: str = ""
    error: str = ""


class BatchJobCreated(BaseModel):
    """Response when a batch job is started."""

    jobId: str
    status: str = "queued"
    total: int


class BatchLigandProgress(BaseModel):
    """Progress for a single ligand in a batch job."""

    ligandIndex: int
    label: str
    status: str
    affinity: float | None = None
    error: str = ""


class BatchJobStatus(BaseModel):
    """Status of a batch docking job."""

    jobId: str
    status: str
    progress: int = 0
    totalLigands: int = 0
    completedLigands: int = 0
    failedLigands: int = 0
    currentLigand: str = ""
    ligands: list[BatchLigandProgress] = Field(default_factory=list)
    error: str | None = None
    elapsedMs: int | None = None


class BatchJobResult(BaseModel):
    """Result of a completed batch docking job."""

    jobId: str
    status: str = "completed"
    results: list[BatchLigandResult]
    total: int
    completed: int
    failed: int
    elapsedMs: int | None = None


class BatchDockingResponse(BaseModel):
    """Batch docking results."""

    results: list[BatchLigandResult]
    total: int
    completed: int
    failed: int
