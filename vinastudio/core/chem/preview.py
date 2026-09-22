"""Renderable copies of a source structure, for the 3D viewport.

The viewport cannot draw a PDBQT (no bond orders, no non-polar hydrogens) and
cannot draw mmCIF at all, so it draws a converted copy: a PDB for a receptor and
an SDF for a ligand. Producing that copy when a file is inspected is what lets
the interface show a structure as soon as it is loaded, rather than only after
the user has prepared it.
"""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from vinastudio.core.chem.export import pdbqt_to_pdb, poses_to_sdf
from vinastudio.core.chem.formats import detect_format, is_supported
from vinastudio.core.chem.ligand_prep import read_mol
from vinastudio.core.chem.mmcif import mmcif_to_pdb
from vinastudio.core.chem.pdbqt import parse_pdbqt
from vinastudio.core.errors import InvalidInputError, UnsupportedFormatError

#: Suffix of the copy written for each kind, which the artifact records.
RECEPTOR_SUFFIX = "pdb"
LIGAND_SUFFIX = "sdf"


def _require(path: str | Path, kind: str) -> tuple[Path, str]:
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")
    if not is_supported(file_path, kind):
        expected = ".pdb .ent .cif .mmcif" if kind == "receptor" else ".mol .sdf .mol2 .pdb"
        raise UnsupportedFormatError(
            f"unsupported {kind} extension {file_path.suffix!r}; expected one of {expected}"
        )
    return file_path, detect_format(file_path) or file_path.suffix.lstrip(".")


def renderable_receptor(path: str | Path) -> str:
    """Return PDB text a 3D viewer can load for a receptor file."""
    file_path, fmt = _require(path, "receptor")

    if fmt == "pdb":
        return file_path.read_text(encoding="utf-8", errors="replace")
    if fmt in ("cif", "mmcif"):
        return mmcif_to_pdb(file_path.read_text(encoding="utf-8", errors="replace"))
    if fmt == "pdbqt":
        return pdbqt_to_pdb(file_path)
    raise UnsupportedFormatError(f"cannot render a {fmt} receptor")


def renderable_ligand(path: str | Path) -> str:
    """Return SDF text a 3D viewer can load for a ligand file.

    A file that only has 2D coordinates is written as it is: the viewport shows
    the molecule flat rather than pretending it has a conformation, and the
    inspection report already says the coordinates are 2D.
    """
    file_path, fmt = _require(path, "ligand")

    if fmt == "pdbqt":
        # A PDBQT carries no bond orders, so the SDF is rebuilt from the SMILES
        # Meeko recorded in its header. Only the first record is kept: a docking
        # output holds one pose per model, and drawing them all on top of each
        # other says less than drawing one.
        document = parse_pdbqt(
            file_path.read_text(encoding="utf-8", errors="replace"), source=str(file_path)
        )
        sdf = poses_to_sdf(document).sdf
        first = sdf.split("$$$$", 1)[0].rstrip()
        return f"{first}\n$$$$\n"

    mol, _ = read_mol(file_path)
    block = Chem.MolToMolBlock(mol)
    if block is None:
        raise InvalidInputError(f"could not convert {file_path.name} to MOL block")
    # Ensure the output is valid SDF (with terminator) so 3Dmol's parser
    # can handle it, including single-atom molecules like metal ions.
    return f"{block.rstrip()}\n$$$$\n"


def renderable(path: str | Path, kind: str) -> tuple[str, str]:
    """Return ``(text, suffix)`` for either kind, for the artifact to record."""
    if kind == "receptor":
        return renderable_receptor(path), RECEPTOR_SUFFIX
    if kind == "ligand":
        return renderable_ligand(path), LIGAND_SUFFIX
    raise InvalidInputError(f"unknown molecule kind: {kind}")
