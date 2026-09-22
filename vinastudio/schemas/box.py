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
