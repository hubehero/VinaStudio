"""mmCIF format support using gemmi.

Converts mmCIF structures to PDB format for use with Meeko's Polymer.
Gemmi handles the complex mmCIF parsing including:
- Multi-model structures (uses first model)
- Missing residues (gaps in numbering)
- Alternate conformations (uses first conformer)
- Non-standard residues (passes through as HETATM)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vinastudio.core.chem.pdb_lines import WATER_RESIDUES

log = logging.getLogger(__name__)


@dataclass(slots=True)
class _ResidueInfo:
    name: str
    atoms: int
    is_water: bool
    is_hetero: bool


def mmcif_to_pdb(text: str) -> str:
    """Convert mmCIF content to PDB format using gemmi.

    Parameters
    ----------
    text : str
        Raw mmCIF file content.

    Returns
    -------
    str
        PDB-formatted string suitable for Meeko's Polymer.from_pdb_string().

    Raises
    ------
    ValueError
        If gemmi cannot parse the mmCIF content.
    """
    import gemmi

    structure = gemmi.read_structure_string(text, format=gemmi.CoorFormat.Mmcif)

    if len(structure) == 0:
        raise ValueError("mmCIF structure contains no atoms")

    # Meeko's Polymer reads one model; the contract says "first model", and the
    # sequence extractor already uses structure[0]. Keep only that model so a
    # multi-model file cannot be handed to the receptor preparation whole.
    if len(structure) > 1:
        del structure[1:]
    return structure.make_pdb_string()


def _iter_mmcif_residues(text: str) -> dict[str, _ResidueInfo]:
    """Parse mmCIF and return residue info keyed by 'chain:seqid'."""
    import gemmi

    structure = gemmi.read_structure_string(text, format=gemmi.CoorFormat.Mmcif)

    if len(structure) == 0:
        return {}

    model = structure[0]
    residues: dict[str, _ResidueInfo] = {}

    # model is iterable and yields Chain objects
    for chain in model:
        # chain is iterable and yields Residue objects
        for residue in chain:
            chain_name = chain.name
            seqid = str(residue.seqid)
            key = f"{chain_name}:{seqid}"
            if key not in residues:
                residues[key] = _ResidueInfo(
                    name=residue.name,
                    atoms=0,
                    is_water=residue.name in WATER_RESIDUES,
                    # het_flag == 'H' means HETATM (ligands, water, ions)
                    is_hetero=str(residue.het_flag) == "H",
                )
            # residue is iterable and yields Atom objects
            residues[key].atoms += sum(1 for _ in residue)

    return residues


def scan_mmcif_residues(text: str) -> dict[str, _ResidueInfo]:
    """Scan mmCIF content for residue information without full conversion.

    Returns a dict keyed by chain:residue for compatibility with PDB scanning.
    """
    return _iter_mmcif_residues(text)
