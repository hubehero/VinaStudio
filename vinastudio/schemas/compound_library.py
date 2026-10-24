"""Contracts for online compound search and download."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CompoundSourceId = Literal["pubchem", "chembl"]
CompoundSearchMode = Literal["text", "similarity", "substructure"]


class CompoundSearchRequest(BaseModel):
    source: CompoundSourceId
    mode: CompoundSearchMode = "text"
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=25, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    threshold: int = Field(default=85, ge=40, le=100)


class CompoundHit(BaseModel):
    source: CompoundSourceId
    id: str
    name: str = ""
    formula: str | None = None
    molecularWeight: float | None = None
    smiles: str | None = None
    inchiKey: str | None = None
    score: float | None = None
    has3D: bool = False
    license: str
    sourceUrl: str
    properties: dict[str, Any] = Field(default_factory=dict)


class CompoundSearchPage(BaseModel):
    source: CompoundSourceId
    mode: CompoundSearchMode
    total: int
    offset: int
    limit: int
    results: list[CompoundHit]
    warnings: list[str] = Field(default_factory=list)


class CompoundFetchRequest(BaseModel):
    source: CompoundSourceId
    id: str = Field(min_length=1, max_length=100)


class CompoundFetchResponse(BaseModel):
    path: str
    name: str
    bytes: int
    source: CompoundSourceId
    sourceId: str
    format: Literal["sdf"] = "sdf"
    has3D: bool
    license: str


class CompoundSourceInfo(BaseModel):
    id: CompoundSourceId
    label: str
    license: str
    capabilities: list[CompoundSearchMode]
    note: str = ""
