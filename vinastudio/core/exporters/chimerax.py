"""A small ChimeraX command file for a complex PDB."""

from __future__ import annotations


def chimerax_script(
    complex_name: str = "complex",
    *,
    ligand_chain: str = "L",
    ligand_resseq: int = 1,
) -> str:
    selector = f"#{1}/{ligand_chain}:{ligand_resseq}"
    return "\n".join(
        [
            f"open {complex_name}.pdb",
            "cartoon #1",
            "show #1",
            f"style {selector} stick",
            f"color {selector} green",
            f"select {selector}",
            "view",
            "",
        ]
    )
