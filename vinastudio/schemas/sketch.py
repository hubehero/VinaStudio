"""Contracts for the sketch chemistry endpoints (TASK-25).

The response field names are the frontend contract and are camelCase exactly
as ``web/src/types/api.ts`` declares them — Pydantic v2 silently drops
snake_case keywords when a model is constructed with them (HANDBOOK §7), and
the canvas reads ``implicitH`` by that name.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SketchAtomPayload(BaseModel):
    id: int
    symbol: str
    x: float
    y: float
    charge: int = 0
    radical: int = Field(default=0, ge=0)


class SketchBondPayload(BaseModel):
    a1: int
    a2: int
    order: float = 1.0
    stereo: int = Field(default=0, ge=0, le=2)


class SketchAnalyzeRequest(BaseModel):
    atoms: list[SketchAtomPayload]
    bonds: list[SketchBondPayload] = Field(default_factory=list)


class SketchRingPayload(BaseModel):
    atomIds: list[int]
    center: tuple[float, float]


class SketchAnalyzeResponse(BaseModel):
    smiles: str | None
    implicitH: dict[int, int]
    problems: list[int]
    rings: list[SketchRingPayload]
    error: str | None = None


class SketchCleanupResponse(BaseModel):
    """``/sketch/cleanup`` answer: original atom id -> Angstrom, chemical frame.

    Same body shape as analyze (``SketchAnalyzeRequest``); only the answer
    model is new.  JSON turns the int keys into strings on the wire — the
    canvas string-indexes ``positions`` exactly like ``implicitH``.
    """

    positions: dict[int, tuple[float, float]]


class SketchLayoutRequest(BaseModel):
    """``/sketch/layout`` body: one SMILES string to lay out (TASK-26 C5)."""

    smiles: str = Field(min_length=1)


class SketchLayoutResponse(BaseModel):
    """Whole-drawing answer.

    Atoms/bonds reuse the analyze payload shapes: the client converts their
    Angstrom coordinates with the same helper it already uses for cleanup.
    """

    atoms: list[SketchAtomPayload]
    bonds: list[SketchBondPayload]
