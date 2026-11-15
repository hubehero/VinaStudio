"""Expected heavy atoms for the standard amino acids.

The receptor preparation report uses this table to say which residues are
incomplete. It is deliberately a **heavy-atom** table: hydrogens are added from
the template/protonation state, so a missing hydrogen is not the same kind of
problem as a missing side-chain carbon.

Source: wwPDB Chemical Component Dictionary residue definitions (the standard
amino-acid atom sets). Variant names that differ only by protonation state or
crystallographic convention are mapped to their parent residue; the mapping is
about atom names, not about asserting a protonation state.
"""

from __future__ import annotations

from typing import Final

STANDARD_RESIDUES: Final[dict[str, frozenset[str]]] = {
    "ALA": frozenset({"N", "CA", "C", "O", "CB"}),
    "ARG": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD", "NE", "CZ", "NH1", "NH2"}),
    "ASN": frozenset({"N", "CA", "C", "O", "CB", "CG", "OD1", "ND2"}),
    "ASP": frozenset({"N", "CA", "C", "O", "CB", "CG", "OD1", "OD2"}),
    "CYS": frozenset({"N", "CA", "C", "O", "CB", "SG"}),
    "GLN": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD", "OE1", "NE2"}),
    "GLU": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD", "OE1", "OE2"}),
    "GLY": frozenset({"N", "CA", "C", "O"}),
    "HIS": frozenset({"N", "CA", "C", "O", "CB", "CG", "ND1", "CD2", "CE1", "NE2"}),
    "ILE": frozenset({"N", "CA", "C", "O", "CB", "CG1", "CG2", "CD1"}),
    "LEU": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD1", "CD2"}),
    "LYS": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD", "CE", "NZ"}),
    "MET": frozenset({"N", "CA", "C", "O", "CB", "CG", "SD", "CE"}),
    "PHE": frozenset(
        {"N", "CA", "C", "O", "CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ"}
    ),
    "PRO": frozenset({"N", "CA", "C", "O", "CB", "CG", "CD"}),
    "SER": frozenset({"N", "CA", "C", "O", "CB", "OG"}),
    "THR": frozenset({"N", "CA", "C", "O", "CB", "OG1", "CG2"}),
    "TRP": frozenset(
        {
            "N",
            "CA",
            "C",
            "O",
            "CB",
            "CG",
            "CD1",
            "CD2",
            "NE1",
            "CE2",
            "CE3",
            "CZ2",
            "CZ3",
            "CH2",
        }
    ),
    "TYR": frozenset(
        {"N", "CA", "C", "O", "CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ", "OH"}
    ),
    "VAL": frozenset({"N", "CA", "C", "O", "CB", "CG1", "CG2"}),
    # Selenomethionine is common in crystallographic structures and has its own
    # atom name (SE); treating it as MET would falsely report SD as missing.
    "MSE": frozenset({"N", "CA", "C", "O", "CB", "CG", "SE", "CE"}),
}

#: Names that differ only by protonation/crystallographic convention.
ALIASES: Final[dict[str, str]] = {
    "HID": "HIS",
    "HIE": "HIS",
    "HIP": "HIS",
    "HSD": "HIS",
    "HSE": "HIS",
    "HSP": "HIS",
    "CYX": "CYS",
    "CYM": "CYS",
    "ASH": "ASP",
    "GLH": "GLU",
    "LYN": "LYS",
}


def expected_heavy_atoms(residue_name: str) -> frozenset[str] | None:
    """Expected heavy-atom names, or ``None`` when this residue is not assessed."""
    name = residue_name.strip().upper()
    name = ALIASES.get(name, name)
    return STANDARD_RESIDUES.get(name)


def missing_heavy_atoms(
    residue_name: str,
    present: set[str] | frozenset[str],
) -> tuple[str, ...] | None:
    """Missing heavy-atom names, sorted; ``None`` when the residue is not assessed."""
    expected = expected_heavy_atoms(residue_name)
    if expected is None:
        return None
    return tuple(sorted(expected - {atom.strip().upper() for atom in present}))
