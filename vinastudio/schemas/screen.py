"""Headless ``screen.json`` contract (version 1.0)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vinastudio.schemas.job import BoxConfig, DockingParameters, ReceptorInput


class ScreenEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    name: str = Field(min_length=1)
    sdfPath: str | None = None
    pdbqtPath: str | None = None


class ScreenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    receptor: ReceptorInput
    libraryPath: str = Field(min_length=1)
    entries: list[ScreenEntry] | None = None
    box: BoxConfig
    parameters: DockingParameters = Field(default_factory=DockingParameters)
    labelsPath: str | None = None
    enrichmentAlpha: float = Field(default=20.0, gt=0)

    @model_validator(mode="after")
    def _screening_rules(self) -> ScreenConfig:
        if self.box.source != "manual":
            raise ValueError("screening needs a manual box; a library has no single ligand")
        if self.entries is not None and not self.entries:
            raise ValueError("entries must not be empty; omit it to use the library index")
        return self
