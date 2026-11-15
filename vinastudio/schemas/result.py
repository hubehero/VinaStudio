"""Headless ``result.json`` contract (version 1.0).

This is the machine-readable product of ``vinastudio-cli dock``. It is built
only from ``core`` objects; the JSON Schema under ``schemas/`` is generated from
these models. Readers ignore unknown fields so minor versions can add data.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RESULT_SCHEMA_VERSION = "1.0"
Severity = Literal["error", "warning"]


class SoftwareInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "vinastudio"
    version: str


class EngineInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: str
    backend: str
    scoring: str


class InputFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    sha256: str
    format: str
    bytes: int | None = None


class InputFiles(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receptor: InputFile
    ligand: InputFile
    reference: InputFile | None = None


class PreparationBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receptor: dict[str, Any]
    ligand: dict[str, Any]


class SearchSpace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    center: tuple[float, float, float]
    size: tuple[float, float, float]
    spacing: float
    forceEvenVoxels: bool
    source: str
    sourceDetail: str | None = None


class ResultParameters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scoring: str
    exhaustiveness: int
    nPoses: int
    energyRange: float
    minRmsd: float
    maxEvals: int
    cpu: int
    seed: int
    noRefine: bool
    engine: str
    verbosity: int
    flexReceptorPath: str | None = None


class Artifacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receptorPdbqt: str | None = None
    receptorPdb: str | None = None
    ligandPdbqt: str | None = None
    ligandSdf: str | None = None
    posesPdbqt: str | None = None
    posesSdf: str | None = None
    flexPdbqt: str | None = None


class FindingRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    severity: Severity
    message_key: str
    detail: dict[str, Any] = Field(default_factory=dict)


class PoseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rank: int
    affinity: float
    rmsdLower: float
    rmsdUpper: float
    rmsdToReference: float | None = None
    worstCheck: Severity | None = None
    checks: list[FindingRecord] = Field(default_factory=list)


class ReferenceValidation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    matched: bool | None = None


class ProjectChecks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    errors: int = 0
    warnings: int = 0
    poses: int = 0


class ValidationBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reference: ReferenceValidation | None = None
    projectChecks: ProjectChecks = Field(default_factory=ProjectChecks)
    posebusters: dict[str, Any] | None = None


class Provenance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    createdAt: str
    host: str
    cwd: str
    command: str
    environment: dict[str, str] = Field(default_factory=dict)
    git: dict[str, Any] = Field(default_factory=dict)


class DockResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schemaVersion: Literal["1.0"] = RESULT_SCHEMA_VERSION
    software: SoftwareInfo
    engine: EngineInfo
    inputs: InputFiles
    preparation: PreparationBlock
    searchSpace: SearchSpace
    parameters: ResultParameters
    artifacts: Artifacts = Field(default_factory=Artifacts)
    poses: list[PoseRecord] = Field(default_factory=list)
    validation: ValidationBlock = Field(default_factory=ValidationBlock)
    analysis: dict[str, Any] | None = None
    provenance: Provenance
