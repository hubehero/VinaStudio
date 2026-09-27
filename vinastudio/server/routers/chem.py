"""Sketch editor chemistry endpoints (TASK-25).

Thin argument mapper: schema in, core call, contract out.  Domain errors
travel up untouched — ``app.py`` maps them once (HANDBOOK §4.6), so there is
no per-endpoint try/except here by design.
"""

from __future__ import annotations

from fastapi import APIRouter

from vinastudio.core.chem import sketch
from vinastudio.schemas.sketch import (
    SketchAnalyzeRequest,
    SketchAnalyzeResponse,
    SketchAtomPayload,
    SketchBondPayload,
    SketchCleanupResponse,
    SketchLayoutRequest,
    SketchLayoutResponse,
    SketchRingPayload,
)

router = APIRouter(prefix="/chem", tags=["chem"])


def _atoms(payload: SketchAnalyzeRequest) -> list[sketch.SketchAtom]:
    return [
        sketch.SketchAtom(a.id, a.symbol, a.x, a.y, a.charge, a.radical)
        for a in payload.atoms
    ]


def _bonds(payload: SketchAnalyzeRequest) -> list[sketch.SketchBond]:
    return [sketch.SketchBond(b.a1, b.a2, b.order, b.stereo) for b in payload.bonds]


@router.post("/sketch/analyze", response_model=SketchAnalyzeResponse)
def analyze_sketch(payload: SketchAnalyzeRequest) -> SketchAnalyzeResponse:
    """Chemical feedback for the drawing.

    Invalid *chemistry* answers 200 with ``smiles=null`` and a human reason
    (the canvas is mid-edit by definition); invalid *requests* — empty canvas,
    unknown symbol, dangling bond — raise InvalidInputError and become 422.
    """
    result = sketch.analyze(atoms=_atoms(payload), bonds=_bonds(payload))
    return SketchAnalyzeResponse(
        smiles=result.smiles,
        implicitH=result.implicit_h,
        problems=result.problems,
        rings=[
            SketchRingPayload(atomIds=list(ring.atom_ids), center=ring.center)
            for ring in result.rings
        ],
        error=result.error,
    )


@router.post("/sketch/cleanup", response_model=SketchCleanupResponse)
def cleanup_sketch(payload: SketchAnalyzeRequest) -> SketchCleanupResponse:
    """Recompute 2D coordinates (rdDepictor + 1.5 A mean bonds).

    Topology never changes; bad *requests* reuse the analyze 422 path, and an
    un-lay-out-able graph also lands as InvalidInputError rather than a 500.
    """
    return SketchCleanupResponse(
        positions=sketch.cleanup_coords(atoms=_atoms(payload), bonds=_bonds(payload))
    )


@router.post("/sketch/layout", response_model=SketchLayoutResponse)
def layout_sketch(payload: SketchLayoutRequest) -> SketchLayoutResponse:
    """SMILES → whole-drawing replacement (TASK-26 C5).

    Unparseable input is a 422 with a human reason — InvalidInputError
    travels up untouched and ``app.py`` maps it once.  Coordinates follow the
    cleanup convention (Angstrom, chemical frame); keywords match the model
    fields exactly (HANDBOOK §7).
    """
    layout = sketch.layout_smiles(payload.smiles)
    return SketchLayoutResponse(
        atoms=[
            SketchAtomPayload(
                id=atom.id,
                symbol=atom.symbol,
                x=atom.x,
                y=atom.y,
                charge=atom.charge,
                radical=atom.radical,
            )
            for atom in layout.atoms
        ],
        bonds=[
            SketchBondPayload(
                a1=bond.a1,
                a2=bond.a2,
                order=float(bond.order),
                stereo=bond.stereo,
            )
            for bond in layout.bonds
        ],
    )
