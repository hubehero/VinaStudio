"""Chemical file format detection and the pipeline's vocabulary."""

from __future__ import annotations

import enum
from pathlib import Path

from vinastudio.config import LIGAND_INPUT_SUFFIXES, RECEPTOR_INPUT_SUFFIXES


class LigandFormat(enum.StrEnum):
    """Input formats Meeko can parameterise into a ligand PDBQT."""

    MOL = "mol"
    SDF = "sdf"
    MOL2 = "mol2"
    PDB = "pdb"
    PDBQT = "pdbqt"


class ReceptorFormat(enum.StrEnum):
    """Input formats the receptor pipeline accepts."""

    PDB = "pdb"
    CIF = "cif"
    MMCIF = "mmcif"
    ENT = "ent"
    PDBQT = "pdbqt"


#: Suffix aliases that map onto a canonical format.
_ALIASES: dict[str, str] = {
    "mdl": "mol",
    "mol": "mol",
    "sd": "sdf",
    "sdf": "sdf",
    "mol2": "mol2",
    "pdb": "pdb",
    "ent": "pdb",
    "cif": "cif",
    "mmcif": "cif",
    "pdbqt": "pdbqt",
}

LIGAND_SUFFIXES = (*LIGAND_INPUT_SUFFIXES, ".pdbqt")
RECEPTOR_SUFFIXES = (*RECEPTOR_INPUT_SUFFIXES, ".pdbqt")

#: Extensions that only carry connectivity, never 3D coordinates.
_TWO_D_ONLY = frozenset({".mol"})

#: Extensions whose hydrogens are usually implicit and must be added.
USUALLY_IMPLICIT_HYDROGENS = frozenset({".mol", ".mol2", ".pdb"})

#: Qt file-dialog filters, so the native dialog and the API agree on what is
#: selectable. Kept here rather than in the web layer to have one definition.
LIGAND_FILTER = (
    "Ligand files (*.mol *.sdf *.mol2 *.pdb *.pdbqt);;"
    "MDL molfile (*.mol);;"
    "SD file (*.sdf);;"
    "Mol2 (*.mol2);;"
    "PDB (*.pdb);;"
    "PDBQT (*.pdbqt)"
)
RECEPTOR_FILTER = (
    "Receptor files (*.pdb *.cif *.mmcif *.ent *.pdbqt);;"
    "PDB (*.pdb *.ent);;"
    "mmCIF (*.cif *.mmcif);;"
    "PDBQT (*.pdbqt)"
)


def normalise_suffix(path: str | Path) -> str:
    """Return the lowercase suffix including the dot, e.g. ``.sdf``."""
    return Path(path).suffix.lower()


def detect_format(path: str | Path) -> str | None:
    """Map a filename onto a canonical format name, or ``None`` if unknown."""
    return _ALIASES.get(normalise_suffix(path).lstrip("."))


def is_supported(path: str | Path, kind: str) -> bool:
    """Check a path against the accepted suffixes for ``ligand`` or ``receptor``."""
    suffixes = LIGAND_SUFFIXES if kind == "ligand" else RECEPTOR_SUFFIXES
    return normalise_suffix(path) in suffixes


def requires_3d_generation(path: str | Path) -> bool:
    """Whether the format cannot be trusted to carry coordinates.

    An MDL molfile may hold either 2D or 3D coordinates; the caller still has to
    inspect the conformer, so this is a hint for the UI, not a decision.
    """
    return normalise_suffix(path) in _TWO_D_ONLY
