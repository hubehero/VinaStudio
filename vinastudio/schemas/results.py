"""Response contracts for the results search API.

Field names mirror ``web/src/types/api.ts`` verbatim — the wire contract is
owned by the design doc §3, and pydantic v2 silently drops snake_case
keywords, so construction sites must pass exactly these names.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.schemas.docking import (
    IfpClusterRow,
    IfpResidue,
    IfpType,
    PoseInfo,
)


class ResultRunSummary(BaseModel):
    """One indexed run, as shown in the search table (design §3)."""

    jobId: str
    label: str
    createdAt: float
    receptor: str
    scoring: str
    status: Literal["completed", "failed", "cancelled"]
    bestAffinity: float | None = None
    isBatch: bool
    matchedLigand: str | None = None


class ResultRunDetail(ResultRunSummary):
    """A run expanded for the compare dialog (design §3)."""

    params: dict[str, Any] | None = None
    nPoses: int = 0
    elapsedMs: int | None = None
    poses: list[PoseInfo] = Field(default_factory=list)


# ── interaction-fingerprint grouping (TASK-16) ──────────────────────────────


class IfpGroupLigand(BaseModel):
    """One ligand input of ``POST /api/results/ifp-cluster``."""

    model_config = ConfigDict(extra="forbid")

    label: str
    pdbqtPath: str


class IfpGroupRequest(BaseModel):
    """Body of ``POST /api/results/ifp-cluster`` (2–200 ligands, paths must
    resolve inside the active workspace)."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str
    ligands: list[IfpGroupLigand] = Field(min_length=2, max_length=200)
    cutoff: float = Field(default=0.5, ge=0, le=1)


class IfpGroupLigandRow(BaseModel):
    """One ligand row of the grouping matrix.

    ``pairs`` are the fingerprint bits (residue index, type order) the shared
    ``IfpMatrix`` draws — the same shape ``IfpFingerprint`` carries for poses
    (coordinator answer 2026-10-10, Q1 方案 A).
    """

    index: int
    label: str
    nContacts: int
    cluster: int
    pairs: list[tuple[int, int]]


class IfpGroupResponse(BaseModel):
    """Response of ``POST /api/results/ifp-cluster`` (report-only, no cache)."""

    residues: list[IfpResidue]
    types: list[IfpType]
    ligands: list[IfpGroupLigandRow]
    clusters: list[IfpClusterRow]
    nClusters: int
    cutoff: float
    matrix: list[list[float]]
