"""Request and response models for the docking endpoints.

The HTTP contract is deliberately separate from the ``core`` dataclasses so the
API surface can evolve independently of internal refactoring.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    engine: Literal["vina", "vina-cli"] = Field(
        default="vina",
        description=(
            "Docking backend. 'vina' means the Vina engine, running whichever way "
            "this machine can (Python module if installed, otherwise the official "
            "command-line binary); 'vina-cli' asks for the binary explicitly."
        ),
    )
    preparation: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compact receptor-preparation summary persisted in job.json for the "
            "Methods text; it is metadata only and never changes docking."
        ),
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
    #: The request the job actually ran with (the same dict persisted in
    #: ``job.json``), minus the inline ligand string. The report's "Methods"
    #: text is generated from these values, so they must be the real ones
    #: rather than whatever the form currently shows.
    params: dict[str, Any] | None = None
    isEnsemble: bool = False
    bestReceptor: str | None = None
    ensembleRows: list[EnsembleRow] = Field(default_factory=list)


class DockingJobSummary(BaseModel):
    """Compact representation for the jobs list.

    Field names are the response contract — the router must pass the same
    camelCase keywords (``elapsed_ms=`` is silently dropped otherwise).
    """

    jobId: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int
    stage: str | None = None
    scoring: ScoringFunction
    elapsedMs: int | None = None
    # History rows (TASK-07): when it ran, what to call it, how it scored.
    createdAt: float = 0.0
    label: str = ""
    bestAffinity: float | None = None
    isBatch: bool = False
    isEnsemble: bool = False


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
    #: Kept for shape compatibility with the docking request, and **ignored**:
    #: Vina's randomisation seeds itself, so no value here can replay a run —
    #: measured on both backends (2026-10-15).
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


class ImportBundleResponse(BaseModel):
    """The imported run is a new completed job, never the original one."""

    jobId: str
    label: str


class ExportBundleRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{job_id}/export-bundle``.

    ``include`` drives both the zip contents and whether the HTML report
    inlines the 2D diagram — the two must stay in step so an unchecked item
    never leaves a dangling reference in the report.
    """

    model_config = ConfigDict(extra="forbid")

    include: list[Literal["sdf", "csv", "config", "svg2d", "html"]] = Field(
        min_length=1,
        description="Bundle members to write; the zip contains exactly these.",
    )
    svg2d: str | None = Field(
        default=None,
        description="Serialized 2D interaction diagram (SVG source).",
    )
    lang: Literal["zh-CN", "en-US"] = Field(
        default="zh-CN",
        description="Report language; follows the interface language.",
    )


class PoseFindingModel(BaseModel):
    """One geometric health-check finding for a pose.

    Mirrors ``core.chem.pose_validation.Finding`` for the HTTP boundary
    (camelCase keys; ``message_key`` becomes ``messageKey``).
    """

    code: str
    severity: Literal["error", "warning"]
    messageKey: str
    detail: dict[str, object] = Field(default_factory=dict)


class ValidatePosesRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{id}/validate``.

    Box and reference are optional: omitting them skips the corresponding
    checks rather than failing the request (missing data is not an error).
    """

    model_config = ConfigDict(extra="forbid")

    poseIndex: int | None = Field(
        default=None,
        ge=1,
        description="1-based pose index; omit (or null) to validate every pose.",
    )
    center: tuple[float, float, float] | None = Field(
        default=None,
        description="Box centre; required with size for out_of_box.",
    )
    size: tuple[float, float, float] | None = Field(
        default=None,
        description="Box edge lengths; required with center for out_of_box.",
    )
    referenceSdfPath: str | None = Field(
        default=None,
        description="Prepared (not docked) ligand SDF path used as geometric reference.",
    )
    enabled: list[str] | None = Field(
        default=None,
        description="Subset of check codes to run; null runs all available checks.",
    )


class PoseValidationItem(BaseModel):
    """Validation result for one pose."""

    poseIndex: int
    findings: list[PoseFindingModel] = Field(default_factory=list)
    worstSeverity: Literal["error", "warning"] | None = None


class ValidatePosesResponse(BaseModel):
    """Response of ``POST /api/docking/jobs/{id}/validate``.

    Report-only: never modifies coordinates or re-docks.
    """

    jobId: str
    poses: list[PoseValidationItem] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    checksRun: list[str] = Field(default_factory=list)


class RmsdRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{id}/rmsd``.

    Exactly one reference field is required — the co-crystal ligand used as
    the redocking reference.
    """

    model_config = ConfigDict(extra="forbid")

    referencePath: str | None = Field(
        default=None,
        description="Co-crystal ligand path (SDF/MOL/MOL2/PDB).",
    )
    referencePdbqt: str | None = Field(
        default=None,
        description="Co-crystal ligand as PDBQT (converted via the shared export path).",
    )
    threshold: float = Field(
        default=2.0,
        gt=0,
        description=(
            "Success threshold in ångström; 2.0 is the community redocking "
            "convention, not a physical constant."
        ),
    )


class RmsdResponse(BaseModel):
    """Response of ``POST /api/docking/jobs/{id}/rmsd``.

    Report-only: never re-docks or edits coordinates. ``structureMatch=False``
    is a warning (the reference is a different chemical structure, which
    inflates RMSD) — never a rejection.
    """

    jobId: str
    values: list[float]
    threshold: float
    successRate: float
    structureMatch: bool | None = None


class ClusterRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{id}/cluster``."""

    model_config = ConfigDict(extra="forbid")

    cutoff: float = Field(
        default=2.0,
        gt=0,
        description=(
            "Neighbour distance cutoff in ångström; 2.0 is the community "
            "convention (the UI slider offers 1.0–3.0, the API accepts "
            "any positive value so extreme values stay testable)."
        ),
    )


class ClusterItem(BaseModel):
    """One BUTINA cluster; ``centroid`` is a 0-based pose index."""

    members: list[int]
    centroid: int
    size: int
    meanRmsd: float


class ClusterResponse(BaseModel):
    """Response of ``POST /api/docking/jobs/{id}/cluster``.

    Computed on demand and never written into the job result (TASK-07 will
    decide what to persist). ``meanRmsd`` is members' mean distance to the
    centroid — geometry only, no energies involved.
    """

    jobId: str
    cutoff: float
    clusters: list[ClusterItem]
    nClusters: int


# ── interaction fingerprints (TASK-16) ──────────────────────────────────────

#: Contact types in fingerprint bit order; old indices stay stable.
IfpType = Literal[
    "ionic",
    "hydrogen_bond",
    "hydrophobic",
    "halogen_bond",
    "metal_coordination",
    "water_mediated",
]


class IfpJobRequest(BaseModel):
    """Body of ``POST /api/docking/jobs/{id}/ifp``."""

    model_config = ConfigDict(extra="forbid")

    cutoff: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description=(
            "BUTINA distance cutoff on 1 − Tanimoto; 0.5 is the community "
            "convention for fingerprint clustering."
        ),
    )


class IfpResidue(BaseModel):
    """One receptor-residue column of the fingerprint matrix."""

    key: str
    resname: str
    chain: str
    resSeq: int
    icode: str


class IfpFingerprint(BaseModel):
    """One pose's fingerprint: bits as (residue index, type order) pairs."""

    index: int
    pairs: list[tuple[int, int]]
    nContacts: int


class IfpClusterRow(BaseModel):
    """One BUTINA cluster over fingerprints (0-based fingerprint indices)."""

    members: list[int]
    centroid: int
    size: int


class IfpJobResponse(BaseModel):
    """Response of ``POST /api/docking/jobs/{id}/ifp``.

    Fingerprints are cached in the job's ``analysis.json`` (keyed by receptor
    identity + poses text); clustering is recomputed per request because the
    cutoff is a view parameter.
    """

    jobId: str
    residues: list[IfpResidue]
    types: list[IfpType]
    fingerprints: list[IfpFingerprint]
    clusters: list[IfpClusterRow]
    nClusters: int
    cutoff: float
    cached: bool


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


class EnsembleReceptor(BaseModel):
    """One receptor conformation in an ensemble."""

    model_config = ConfigDict(extra="forbid")

    index: int = 0
    path: str
    label: str = ""
    flexPath: str | None = None


class EnsembleDockingRequest(BaseModel):
    """One ligand docked into several receptor conformations (TASK-60-B).

    The conformers must share the coordinate frame; the same box is used for
    every run. This is ensemble docking, not induced fit.
    """

    model_config = ConfigDict(extra="forbid")

    receptors: list[EnsembleReceptor]
    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = Field(default=8, ge=1, le=512)
    nPoses: int = Field(default=20, ge=1, le=100)
    energyRange: float = 3.0
    minRmsd: float = 1.0
    maxEvals: int = 0
    cpu: int = 0
    seed: int = 0
    noRefine: bool = False
    verbosity: int = 1
    spacing: float = 0.375
    forceEvenVoxels: bool = False
    weights: list[float] | None = None
    mapPaths: list[str] | None = None
    engine: Literal["vina", "vina-cli"] = "vina"


class EnsembleRow(BaseModel):
    receptorIndex: int
    label: str
    receptorPath: str
    status: str
    bestAffinity: float | None = None
    nPoses: int = 0
    elapsedMs: int | None = None
    outDir: str = ""
    error: str = ""


class BatchLigandItem(BaseModel):
    """A single ligand in a batch docking request."""

    model_config = ConfigDict(extra="forbid")

    ligandPath: str | None = None
    ligandPdbqtString: str | None = None
    label: str = ""
    """Optional label to distinguish results."""
    prepare: bool = False
    """Prepare a source SDF/MOL before docking (selection runs only)."""


class BatchDockingRequest(BaseModel):
    """Body of ``POST /api/docking/batch``.

    Shares a single receptor + box configuration across all ligands.
    """

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    flexReceptorPath: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    ligands: list[BatchLigandItem] = Field(default_factory=list)
    selectionId: str | None = None
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = 8
    nPoses: int = 20
    energyRange: float = 3.0
    minRmsd: float = 1.0
    cpu: int = 0
    parallelism: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Concurrent ligand workers for this batch (server caps at 4 and by "
            "the memory budget). Omit to use max(1, cpu_count-1)."
        ),
    )
    seed: int = 0
    noRefine: bool = False
    engine: Literal["vina", "vina-cli"] = Field(
        default="vina",
        description=(
            "Docking backend. 'vina' means the Vina engine, running whichever way "
            "this machine can (Python module if installed, otherwise the official "
            "command-line binary); 'vina-cli' asks for the binary explicitly."
        ),
    )

    @model_validator(mode="after")
    def _ligand_source(self) -> BatchDockingRequest:
        if bool(self.selectionId) == bool(self.ligands):
            raise ValueError("give exactly one of ligands or selectionId")
        return self


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
    # TASK-10 移交（TASK-13 §4.6）: best-effort descriptors, null when the
    # source did not parse — never gate the docking itself.
    qed: float | None = None
    lipinskiViolations: int | None = None


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
    # TASK-10 移交（TASK-13 §4.6）: same best-effort pair as the result row.
    qed: float | None = None
    lipinskiViolations: int | None = None


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
