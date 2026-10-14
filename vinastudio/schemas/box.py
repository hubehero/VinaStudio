"""Request and response models for the search box."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.config import DEFAULT_SPACING


class BoxSpec(BaseModel):
    """A box in Vina's own terms: centre, three edge lengths, and grid spacing."""

    model_config = ConfigDict(extra="forbid")

    center: tuple[float, float, float] = Field(description="Angstrom, may be negative")
    size: tuple[float, float, float] = Field(description="Full edge lengths, not half-extents")
    spacing: float = DEFAULT_SPACING
    forceEvenVoxels: bool = False


class BoxMetrics(BoxSpec):
    """A box plus everything derived from it.

    The interface never computes these itself: the voxel rule is Vina's, and
    having one definition in ``core/box.py`` is what keeps the panel from
    disagreeing with what ``write_maps`` will actually accept.
    """

    voxels: list[int]
    gridPoints: list[int]
    volume: float
    canWriteMaps: bool
    limits: list[list[float]]
    warnings: list[str] = Field(default_factory=list)


class AutoboxRequest(BaseModel):
    """Derive a box from the coordinates of a file."""

    model_config = ConfigDict(extra="forbid")

    path: str
    extend: float = Field(
        default=0.0,
        description="Margin added to every side, so each edge grows by twice this",
    )
    spacing: float = DEFAULT_SPACING
    forceEvenVoxels: bool = False
    includeHydrogens: bool = False
    """Off by default: hydrogen positions depend on the tool that added them."""


class AutoboxFromResiduesRequest(AutoboxRequest):
    residues: list[str] = Field(
        default_factory=list,
        description="Residue keys as chain:number, e.g. ['A:315']",
    )


class AutoboxResponse(BaseModel):
    box: BoxMetrics
    points: int
    """How many atoms defined the box, so a wrong selection is visible."""
    source: str


class ConfigText(BaseModel):
    text: str


class PocketRequest(BaseModel):
    """Detect candidate binding sites from the receptor's geometry alone.

    Defaults are the published fpocket parameters (see
    ``vinastudio.core.pocket`` and ``docs/references/``).
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    minRadius: float = Field(default=3.0, gt=0, le=10.0)
    maxRadius: float = Field(default=6.0, gt=0, le=20.0)
    linkMinPairs: int = Field(default=8, ge=1, le=100)
    minSpheres: int = Field(default=35, ge=1, le=1000)
    topK: int = Field(default=5, ge=1, le=20)
    spacing: float = DEFAULT_SPACING
    """Grid spacing of the box each candidate hands back."""


class PocketCandidate(BaseModel):
    """One geometrically detected cavity, with the box it implies.

    Deliberately *candidates*: the geometry says "a ligand could sit here",
    which is not the same claim as a predicted binding site.
    """

    rank: int
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    volume: float
    spheres: int
    score: float
    apolarFraction: float
    box: BoxMetrics


class PocketsResponse(BaseModel):
    pockets: list[PocketCandidate]
    atoms: int
    """Heavy atoms the detection ran on, so a wrong file is visible."""
    params: dict[str, float]
    """The thresholds actually used, echoed back for the record."""


class WriteMapsRequest(BaseModel):
    """Request to write affinity maps to disk."""

    model_config = ConfigDict(extra="forbid")

    receptorPath: str = Field(description="Path to prepared receptor PDBQT.")
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    spacing: float = DEFAULT_SPACING
    forceEvenVoxels: bool = False
    outputPrefix: str = Field(description="Output path prefix (e.g. /path/to/receptor).")


class WriteMapsResponse(BaseModel):
    maps: list[str]
    """List of written map file paths."""
    gpf: str | None = None
    """AutoGrid4 GPF file path, if written."""
