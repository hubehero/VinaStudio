"""PLIP-shaped JSON derived from VinaStudio's six geometric contact rules.

This is a mapping, not a PLIP run: salt bridges remain candidates unless formal
charges are present, halogen bonds are distance-only, and there is no
pi-stacking. The disclaimer and mapping travel with the document.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from vinastudio.core.chem.ifp import (
    DEFAULT_DISTANCE_CUTOFF,
    find_contacts,
    parse_ligand_sdf,
    parse_receptor_atoms,
)

PLIP_TYPES = {
    "ionic": "salt_bridge",
    "hydrogen_bond": "hydrogen_bond",
    "hydrophobic": "hydrophobic",
    "halogen_bond": "halogen_bond",
    "metal_coordination": "metal_complex",
    "water_mediated": "water_bridge",
}


def _atom(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("atom", ""),
        "residue": row.get("residue", ""),
        "chain": row.get("chain", ""),
        "resSeq": row.get("resSeq", ""),
        "element": row.get("element", ""),
        "x": row.get("x"),
        "y": row.get("y"),
        "z": row.get("z"),
    }


def plip_document(
    receptor_path: str | Path,
    pose_sdf: str,
    *,
    distance_cutoff: float = DEFAULT_DISTANCE_CUTOFF,
) -> dict[str, Any]:
    receptor_atoms = parse_receptor_atoms(str(receptor_path))
    ligand_atoms = parse_ligand_sdf(pose_sdf)
    contacts = find_contacts(receptor_atoms, ligand_atoms, distance_cutoff)

    interactions: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for receptor_atom, ligand_atom, distance, contact_type in contacts:
        plip_type = PLIP_TYPES.get(contact_type, contact_type)
        counts[plip_type] += 1
        row: dict[str, Any] = {
            "type": plip_type,
            "projectType": contact_type,
            "distance": round(float(distance), 2),
            "receptor": _atom(receptor_atom),
            "ligand": _atom(ligand_atom),
        }
        water = receptor_atom.get("water")
        if isinstance(water, dict):
            row["water"] = _atom(water)
            row["waterDistance"] = receptor_atom.get("waterDistance")
        interactions.append(row)

    return {
        "schemaVersion": "1.0",
        "source": "vinastudio",
        "format": "plip-shaped",
        "distanceCutoff": distance_cutoff,
        "mapping": PLIP_TYPES,
        "disclaimer": (
            "Derived from VinaStudio's six geometric contact rules. This is not "
            "a PLIP run; salt bridges are candidates when formal charges are "
            "absent, halogen bonds are distance-only, and pi-stacking is not "
            "reported."
        ),
        "interactions": interactions,
        "byType": dict(sorted(counts.items())),
    }
