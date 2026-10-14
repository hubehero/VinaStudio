"""Site-screen contracts: one ligand docked into several candidate boxes (S2).

The point of the exercise is a *ranking*: which of the boxes the detector
proposed actually holds a plausible binding site. Affinities here are produced
with a deliberately low exhaustiveness, so the ordering is meaningful but the
numbers are not comparable with a production docking run — the UI says so, and
so does :class:`SiteScreeningResult`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.schemas.docking import ScoringFunction


class SiteCandidate(BaseModel):
    """One box to try. ``index`` is the caller's id, echoed back on the row."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    label: str = ""
    center: tuple[float, float, float]
    size: tuple[float, float, float]


class SiteScreeningRequest(BaseModel):
    """Body of ``POST /api/sites/start``: one ligand, N candidate boxes."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str = Field(description="Path to prepared receptor PDBQT.")
    flexReceptorPath: str | None = Field(
        default=None, description="Path to flexible sidechain PDBQT (optional)."
    )
    ligandPath: str | None = Field(
        default=None, description="Path to prepared ligand PDBQT."
    )
    ligandPdbqtString: str | None = Field(
        default=None, description="PDBQT content, when the ligand is not on disk."
    )
    candidates: list[SiteCandidate] = Field(min_length=1, max_length=20)
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = Field(
        default=8,
        ge=1,
        le=512,
        description="Deliberately low by default: this is a screen, not a run.",
    )
    nPoses: int = Field(default=10, ge=1, le=100)
    energyRange: float = Field(default=3.0, gt=0)
    minRmsd: float = Field(default=1.0, ge=0)
    maxEvals: int = Field(default=0, ge=0)
    cpu: int = Field(default=0, ge=0)
    seed: int = Field(default=0, ge=0)
    noRefine: bool = False
    verbosity: int = Field(default=1, ge=0, le=2)
    spacing: float = Field(default=0.375, gt=0)
    forceEvenVoxels: bool = False
    weights: list[float] | None = None
    mapPaths: list[str] | None = None
    engine: Literal["vina"] = "vina"


class SiteScreeningCreated(BaseModel):
    jobId: str
    status: str


class SiteRow(BaseModel):
    """One candidate's outcome, joined with the box it was run in."""

    index: int
    label: str
    status: Literal["completed", "failed"]
    rank: int | None = None
    """1-based among scored boxes; ``None`` when the box has no affinity."""
    center: tuple[float, float, float] | None = None
    size: tuple[float, float, float] | None = None
    bestAffinity: float | None = None
    nPoses: int | None = None
    elapsedMs: int | None = None
    error: str | None = None


class SiteScreeningStatus(BaseModel):
    jobId: str
    status: str
    progress: int
    stage: str | None = None
    error: str | None = None
    elapsedMs: int | None = None
    totalCandidates: int
    completedCandidates: int
    failedCandidates: int
    currentLabel: str = ""
    rows: list[SiteRow] = Field(default_factory=list)
    """Rows so far — a screen is useful while it fills in, not only at the end."""


class SiteScreeningResult(BaseModel):
    jobId: str
    status: str
    scoring: str
    exhaustiveness: int
    rows: list[SiteRow] = Field(default_factory=list)
    bestAffinity: float | None = None
    bestIndex: int | None = None
    elapsedMs: int | None = None
