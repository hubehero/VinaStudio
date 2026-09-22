"""Request and response models for the preparation endpoints.

These are deliberately separate from the ``core`` dataclasses: the HTTP contract
should only change when someone decides it should, not because a domain object
was refactored.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# shared
# --------------------------------------------------------------------------


class FileRef(BaseModel):
    """A file the caller wants acted on, identified by absolute path."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Absolute path chosen through the native dialog or upload.")


class Artifact(BaseModel):
    """A file produced by a run, with the URL the interface can fetch it from."""

    name: str
    path: str
    url: str
    bytes: int
    kind: Literal["pdbqt", "pdb", "sdf", "json", "log", "text"]


class RunInfo(BaseModel):
    runId: str
    directory: str


class FileFilters(BaseModel):
    """Qt dialog filter strings, so native dialogs and the API agree."""

    ligand: str
    receptor: str
    ligandSuffixes: list[str]
    receptorSuffixes: list[str]


class SavedUpload(BaseModel):
    path: str
    name: str
    bytes: int
    suffix: str


class SampleFile(BaseModel):
    name: str
    path: str
    description: str
    bytes: int


class DetectionResponse(BaseModel):
    """What a file holds, and the evidence that decided it."""

    kind: Literal["receptor", "ligand"]
    reason: Literal["extension", "polymer residues", "small molecule"]
    atoms: int
    residues: int
    waters: int
    chains: int
    polymerResidues: int


class RenderableRequest(BaseModel):
    """A structure to convert into something the 3D viewport can draw."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Path to the source structure.")
    kind: Literal["receptor", "ligand"] = Field(
        description="How the file was classified, which decides the output format.",
    )


# --------------------------------------------------------------------------
# ligand
# --------------------------------------------------------------------------


class LigandPreview(BaseModel):
    source: str
    inputFormat: str
    preparable: bool
    atoms: int
    hydrogens: int
    has3dCoordinates: bool
    rotatableBonds: int
    molecularFormula: str | None = None
    molecularWeight: float | None = None
    smiles: str | None = None
    records: int
    notes: list[str] = Field(default_factory=list)


class LigandOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimiseGeometry: bool = True
    embedSeed: int = 0xF00D
    rigidMacrocycles: bool = False
    flexibleAmides: bool = False
    hydrate: bool = False
    doubleBondPenalty: float = 50.0


class LigandReport(BaseModel):
    source: str
    inputFormat: str
    inputAtoms: int
    hydrogensAdded: int
    conformerGenerated: bool
    geometryOptimised: bool
    outputAtoms: int
    outputPolarHydrogens: int
    nonpolarHydrogensRemoved: int
    rotatableBonds: int
    totalCharge: float
    atomTypes: dict[str, int]
    smiles: str | None = None
    warnings: list[str] = Field(default_factory=list)


class LigandPreparationResponse(BaseModel):
    run: RunInfo
    report: LigandReport
    artifacts: list[Artifact]
    pdbqt: str
    """Also returned inline: it is a few kilobytes and the docking call wants it."""


class LigandPrepareRequest(BaseModel):
    """Body of ``POST /api/ligand/prepare``.

    One model rather than two parameters: FastAPI nests multiple body models
    under their parameter names, which would make the payload
    ``{"request": ..., "options": ...}`` for no reason.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    options: LigandOptions = Field(default_factory=LigandOptions)


# --------------------------------------------------------------------------
# receptor
# --------------------------------------------------------------------------


class ReceptorPreview(BaseModel):
    source: str
    inputFormat: str
    preparable: bool
    atoms: int
    residues: int
    chains: int
    waters: list[str] = Field(default_factory=list)
    hetero: list[str] = Field(default_factory=list)
    residueNames: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReceptorOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleteWaters: bool = True
    deleteHetero: bool = True
    flexibleResidues: list[str] = Field(default_factory=list)
    allowBadResidues: bool = False
    normaliseAtomOrder: bool = True


class ReceptorReport(BaseModel):
    source: str
    inputFormat: str
    inputAtoms: int
    inputResidues: int
    deletedWaters: list[str] = Field(default_factory=list)
    deletedHetero: list[str] = Field(default_factory=list)
    normalisedAtomOrder: bool
    validResidues: int
    ignoredResidues: list[str] = Field(default_factory=list)
    flexibleResidues: list[str] = Field(default_factory=list)
    outputAtoms: int
    atomTypes: dict[str, int]
    includeHydrogens: bool
    warnings: list[str] = Field(default_factory=list)
    residueList: list[str] = Field(default_factory=list)


class ReceptorPreparationResponse(BaseModel):
    run: RunInfo
    report: ReceptorReport
    artifacts: list[Artifact]
    hasFlexibleSidechains: bool


class ReceptorPrepareRequest(BaseModel):
    """Body of ``POST /api/receptor/prepare``; see :class:`LigandPrepareRequest`."""

    model_config = ConfigDict(extra="forbid")

    path: str
    options: ReceptorOptions = Field(default_factory=ReceptorOptions)
