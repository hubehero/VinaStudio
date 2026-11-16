"""Headless ``job.json`` contract (version 1.0).

The CLI and Python API read this file; the GUI keeps using its own request
models. Paths are resolved relative to the job file by the caller, not here —
this module only validates the shape.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vinastudio.config import ScoringFunction
from vinastudio.schemas.version import INPUT_VERSION_PATTERN, validate_input_version

JOB_SCHEMA_VERSION = "1.0"
BoxSource = Literal["ligand", "manual"]
EngineName = Literal["vina", "vina-cli"]


class ReceptorPreparationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleteWaters: bool = True
    deleteHetero: bool = True
    allowBadResidues: bool = False
    normaliseAtomOrder: bool = True
    defaultAltloc: str = ""
    keepResidues: list[str] = Field(default_factory=list)
    flexibleResidues: list[str] = Field(default_factory=list)


class LigandPreparationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimiseGeometry: bool = True
    embedSeed: int = 42
    rigidMacrocycles: bool = False
    flexibleAmides: bool = False
    hydrate: bool = False
    doubleBondPenalty: float = Field(default=50.0, gt=0)


class ReceptorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    preparation: ReceptorPreparationOptions = Field(
        default_factory=ReceptorPreparationOptions
    )


class LigandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    preparation: LigandPreparationOptions = Field(
        default_factory=LigandPreparationOptions
    )


class BoxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: BoxSource = "manual"
    center: tuple[float, float, float] | None = None
    size: tuple[float, float, float] | None = None
    extend: float = Field(default=4.0, ge=0)
    spacing: float = Field(default=0.375, gt=0)
    forceEvenVoxels: bool = False

    @model_validator(mode="after")
    def _source_matches_fields(self) -> BoxConfig:
        if self.source == "manual":
            if self.center is None or self.size is None:
                raise ValueError("manual box needs center and size")
            if any(value <= 0 for value in self.size):
                raise ValueError("box size must contain only positive values")
            if not all(math.isfinite(value) for value in (*self.center, *self.size)):
                raise ValueError("box centre and size must be finite")
        else:
            if self.center is not None or self.size is not None:
                raise ValueError("ligand-derived box must not set center or size")
        return self


class DockingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring: ScoringFunction = "vina"
    exhaustiveness: int = Field(default=8, ge=1, le=512)
    nPoses: int = Field(default=9, ge=1, le=100)
    energyRange: float = Field(default=3.0, gt=0)
    minRmsd: float = Field(default=1.0, ge=0)
    maxEvals: int = Field(default=0, ge=0)
    cpu: int = Field(default=0, ge=0)
    seed: int = 42
    noRefine: bool = False
    engine: EngineName = "vina"
    verbosity: int = Field(default=1, ge=0, le=3)
    flexReceptorPath: str | None = None


class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    rmsdThreshold: float = Field(default=2.0, gt=0)


class JobConfig(BaseModel):
    """One headless docking job; the ``--config`` file in the CLI."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = Field(
        default=JOB_SCHEMA_VERSION, pattern=INPUT_VERSION_PATTERN
    )
    receptor: ReceptorInput
    ligand: LigandInput
    box: BoxConfig = Field(default_factory=BoxConfig)
    parameters: DockingParameters = Field(default_factory=DockingParameters)
    reference: ReferenceConfig | None = None

    @field_validator("schemaVersion", mode="before")
    @classmethod
    def _schema_version(cls, value: object) -> str:
        return validate_input_version(value, "job.json")
