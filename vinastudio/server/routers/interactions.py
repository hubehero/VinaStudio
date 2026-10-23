"""Interaction analysis endpoints for protein-ligand complexes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from vinastudio.core.chem.depict import depict_2d
from vinastudio.core.chem.ifp import (
    DEFAULT_DISTANCE_CUTOFF,
    find_contacts,
    parse_ligand_atoms,
    parse_receptor_atoms,
)
from vinastudio.core.errors import InvalidInputError, VinaStudioError, brief_error

log = logging.getLogger(__name__)

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("/analyze")
def analyze_interactions(request: dict[str, Any]) -> dict[str, Any]:
    """Analyze protein-ligand interactions from PDBQT or SDF files.

    This is a simplified analysis that identifies potential interactions
    based on distance and atom types. For more accurate analysis, use
    tools like PLIP or FPocket.
    """
    receptor_path = request.get("receptorPath", "")
    ligand_path = request.get("ligandPath", "")
    ligand_pdbqt = request.get("ligandPdbqtString", "")
    distance_cutoff = request.get("distanceCutoff", DEFAULT_DISTANCE_CUTOFF)

    # The receptor is never optional: the old first check also accepted a bare
    # ligand and silently reported "no interactions" for a contact analysis
    # with no protein in it.
    if not receptor_path:
        raise InvalidInputError("receptorPath is required")

    if not ligand_path and not ligand_pdbqt:
        raise InvalidInputError("ligandPath or ligandPdbqtString is required")

    try:
        interactions = _find_interactions(
            receptor_path=receptor_path,
            ligand_path=ligand_path,
            ligand_pdbqt=ligand_pdbqt,
            distance_cutoff=distance_cutoff,
        )
        # The 2D depiction is an optional extra: contacts must not fail just
        # because bond orders could not be restored (a bare PDBQT without its
        # REMARK SMILES line has no chemistry to draw).
        try:
            depicted: dict[str, Any] | None = depict_2d(ligand_pdbqt or ligand_path)
        # Depiction must never sink the analysis: an unparseable ligand still
        # deserves its contact table.
        except Exception as exc:
            log.warning("ligand depiction unavailable: %s", exc, exc_info=True)
            depicted = None
        return {
            "interactions": interactions,
            "count": len(interactions),
            "depict": depicted,
        }
    except VinaStudioError:
        raise
    except Exception as e:
        log.exception("Failed to analyze interactions")
        raise InvalidInputError(f"failed to analyze interactions: {brief_error(e)}") from e


def _find_interactions(
    receptor_path: str = "",
    ligand_path: str = "",
    ligand_pdbqt: str = "",
    distance_cutoff: float = DEFAULT_DISTANCE_CUTOFF,
) -> list[dict[str, Any]]:
    """Find interactions between receptor and ligand atoms.

    Geometry lives in ``core.chem.ifp``; this wrapper only shapes the wire
    rows, so the contact response contract stays byte-for-byte identical.
    """
    receptor_atoms = parse_receptor_atoms(receptor_path) if receptor_path else []
    ligand_atoms = parse_ligand_atoms(ligand_path, ligand_pdbqt)

    interactions = []
    for r_atom, l_atom, dist, inter_type in find_contacts(
        receptor_atoms, ligand_atoms, distance_cutoff
    ):
        row = {
            "type": inter_type,
            "receptorResidue": r_atom.get("residue", ""),
            "receptorChain": r_atom.get("chain", ""),
            "receptorResSeq": r_atom.get("resSeq", ""),
            "receptorAtom": r_atom.get("atom", ""),
            "receptorX": r_atom["x"],
            "receptorY": r_atom["y"],
            "receptorZ": r_atom["z"],
            "ligandAtom": l_atom.get("atom", ""),
            "ligandX": l_atom["x"],
            "ligandY": l_atom["y"],
            "ligandZ": l_atom["z"],
            "distance": round(dist, 2),
        }
        water = r_atom.get("water")
        if isinstance(water, dict):
            row.update({
                "waterResidue": water.get("residue", ""),
                "waterChain": water.get("chain", ""),
                "waterResSeq": water.get("resSeq", ""),
                "waterAtom": water.get("atom", ""),
                "waterX": water.get("x"),
                "waterY": water.get("y"),
                "waterZ": water.get("z"),
                "waterDistance": r_atom.get("waterDistance"),
                "bridgeDistance": r_atom.get("bridgeDistance"),
            })
        interactions.append(row)

    # Sort by distance
    interactions.sort(key=lambda x: x["distance"])

    return interactions
