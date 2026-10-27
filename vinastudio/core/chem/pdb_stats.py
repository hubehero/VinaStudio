"""Structural statistics that are safe to show without claiming a formula.

A PDB entry has no single molecular formula: it can contain several protein
chains, cofactors, waters and unresolved residues.  For teaching metadata we
report the mass of the modelled polymer only and label it explicitly in the UI.
"""

from __future__ import annotations

from pathlib import Path

import gemmi

WATER_MASS = 18.01528


def polymer_molecular_weight(path: str | Path) -> float | None:
    """Average mass of the polymer residues present in the first model.

    Uses gemmi's tabulated residue masses, subtracts one water per residue and
    adds one water per chain.  Ligands, waters and residues missing from the
    coordinates are excluded, so this is the mass of the observed construct,
    not of the full gene product.
    """
    try:
        structure = gemmi.read_structure(str(path))
    except (OSError, RuntimeError, ValueError):
        return None
    if not structure or len(structure) == 0:
        return None

    total = 0.0
    for chain in structure[0]:
        residue_count = 0
        for residue in chain:
            if residue.entity_type != gemmi.EntityType.Polymer:
                continue
            info = gemmi.find_tabulated_residue(residue.name)
            if info.weight <= 0:
                continue
            total += info.weight - WATER_MASS
            residue_count += 1
        if residue_count:
            total += WATER_MASS
    return round(total, 1) if total > 0 else None
