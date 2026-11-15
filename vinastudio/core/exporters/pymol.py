"""A small PyMOL script for a complex PDB; no PyMOL binary is required."""

from __future__ import annotations


def pymol_script(
    complex_name: str = "complex",
    *,
    ligand_resname: str = "LIG",
) -> str:
    return "\n".join(
        [
            f"load {complex_name}.pdb, {complex_name}",
            f"hide everything, {complex_name}",
            f"show cartoon, {complex_name}",
            f"show sticks, resn {ligand_resname}",
            f"color green, resn {ligand_resname}",
            f"select ligand, resn {ligand_resname}",
            "zoom ligand",
            "",
        ]
    )
