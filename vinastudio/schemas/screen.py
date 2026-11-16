"""Headless ``screen.json`` contract (version 1.0)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vinastudio.schemas.job import BoxConfig, DockingParameters, ReceptorInput
from vinastudio.schemas.version import INPUT_VERSION_PATTERN, validate_input_version

SCREEN_SCHEMA_VERSION = "1.0"


class ScreenEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    name: str = Field(min_length=1)
    sdfPath: str | None = None
    pdbqtPath: str | None = None


class ScreenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = Field(
        default=SCREEN_SCHEMA_VERSION, pattern=INPUT_VERSION_PATTERN
    )
    receptor: ReceptorInput
    libraryPath: str = Field(min_length=1)
    entries: list[ScreenEntry] | None = None
    box: BoxConfig
    parameters: DockingParameters = Field(default_factory=DockingParameters)
    labelsPath: str | None = None
    enrichmentAlpha: float = Field(default=20.0, gt=0)

    @field_validator("schemaVersion", mode="before")
    @classmethod
    def _schema_version(cls, value: object) -> str:
        return validate_input_version(value, "screen.json")

    @model_validator(mode="after")
    def _screening_rules(self) -> ScreenConfig:
        if self.box.source != "manual":
            raise ValueError("screening needs a manual box; a library has no single ligand")
        if self.entries is not None and not self.entries:
            raise ValueError("entries must not be empty; omit it to use the library index")
        return self
