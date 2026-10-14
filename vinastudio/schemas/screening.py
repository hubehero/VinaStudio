"""Request and response models for the virtual screening endpoints (TASK-13).

Wire shapes are fixed by ``exchange/design/TASK-13-vscreen-workbench.md`` §3 —
field names and optionality match the TypeScript contract types exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.config import ScoringFunction

RankingSortBy = Literal["affinity", "qed", "lipinski"]
PrepareState = Literal["none", "done", "failed"]
ImportFailureReason = Literal["parse", "too_large", "cap", "write"]
RunStatus = Literal["running", "completed", "failed", "cancelled"]


class LibrarySummary(BaseModel):
    name: str
    total: int
    prepared: int
    created: float


class LibraryEntry(BaseModel):
    index: int
    name: str
    molWt: float | None = None
    qed: float | None = None
    lipinskiViolations: int | None = None
    prepare: PrepareState = "none"


class LibraryDetail(BaseModel):
    name: str
    total: int
    created: float
    entries: list[LibraryEntry]


class ImportedFailure(BaseModel):
    index: int
    name: str
    reason: ImportFailureReason


class LibraryImportResult(BaseModel):
    name: str
    imported: int
    skipped: int
    failedCount: int
    failed: list[ImportedFailure]


class ScreeningStartRequest(BaseModel):
    """Body of ``POST /api/screening/runs``.

    BatchDockingRequest minus ``ligands`` plus ``library`` (design §3 field
    list); ``minRmsd`` is not on the wire here — the worker default (1.0)
    applies, matching what the batch worker falls back to.
    """

    model_config = ConfigDict(extra="forbid")

    library: str
    receptorPath: str
    flexReceptorPath: str | None = None
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    scoring: ScoringFunction = "vina"
    exhaustiveness: int = Field(default=8, ge=1, le=512)
    nPoses: int = Field(default=20, ge=1, le=100)
    energyRange: float = Field(default=3.0, gt=0)
    cpu: int = 0
    parallelism: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Concurrent ligand workers (server caps at 4 and by the memory "
            "budget). Omit to use max(1, cpu_count-1)."
        ),
    )
    seed: int = 0
    noRefine: bool = False
    engine: Literal["vina"] = "vina"


class ScreeningRunCreated(BaseModel):
    jobId: str


class ScreeningRunSummary(BaseModel):
    jobId: str
    library: str
    createdAt: float
    status: RunStatus
    progress: int
    totalLigands: int
    completedLigands: int
    failedLigands: int
    bestAffinity: float | None = None
    error: str | None = None


class ScreeningRunStatus(ScreeningRunSummary):
    currentLigand: str | None = None
    elapsedMs: int | None = None


class RankingRow(BaseModel):
    rank: int
    ligandIndex: int
    name: str
    affinity: float | None = None
    nPoses: int | None = None
    qed: float | None = None
    lipinskiViolations: int | None = None


class RankingResponse(BaseModel):
    total: int
    rows: list[RankingRow]
