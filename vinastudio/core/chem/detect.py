"""Decide what a structure file is, from its content rather than its name.

`.pdb` and `.pdbqt` say nothing about whether they hold a receptor or a ligand,
and the interface used to guess by inspecting one way and trying the other when
that failed: two round trips, a rule that lived only in the frontend, and a guess
that misfiled a small molecule carrying a couple of waters as a receptor.

The rule here reads the file once and states its evidence, so the interface, the
batch runner and the tests all reach the same conclusion for the same file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vinastudio.core.chem.formats import RECEPTOR_SUFFIXES, detect_format
from vinastudio.core.chem.ligand_prep import inspect_ligand
from vinastudio.core.chem.receptor_prep import inspect_receptor
from vinastudio.core.errors import InvalidInputError, VinaStudioError

Kind = Literal["receptor", "ligand"]
Reason = Literal["extension", "polymer residues", "small molecule"]

#: Extensions that answer the question on their own; the rest have to be read.
_LIGAND_ONLY = frozenset({".sdf", ".mol", ".mol2"})
_RECEPTOR_ONLY = frozenset({".cif", ".mmcif", ".ent"})

#: Polymer residues a structure needs before it is called a receptor. One residue
#: is a small molecule in a protein-shaped file, and the solvent a file happens to
#: carry is not a residue that makes it a receptor.
MIN_POLYMER_RESIDUES = 2

#: What a reader raises when the file is not the shape it expected: the domain
#: errors this application defines, plus the parser and RDKit errors underneath.
_UNREADABLE = (VinaStudioError, ValueError, OSError, RuntimeError)


@dataclass(slots=True)
class Detection:
    """What a file is, and the evidence that decided it."""

    kind: Kind
    reason: Reason
    source: str
    atoms: int = 0
    residues: int = 0
    waters: int = 0
    chains: int = 0

    @property
    def polymer_residues(self) -> int:
        """Residues that are not solvent."""
        return max(0, self.residues - self.waters)


def _kind_by_extension(suffix: str) -> Kind | None:
    if suffix in _LIGAND_ONLY:
        return "ligand"
    if suffix in _RECEPTOR_ONLY:
        return "receptor"
    return None


def detect_kind(path: str | Path) -> Detection:
    """Return what the file at *path* is, with the evidence behind the answer."""
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")

    fmt = detect_format(file_path) or file_path.suffix.lstrip(".")
    suffix = f".{fmt}"

    decided = _kind_by_extension(suffix)
    if decided is not None:
        return Detection(kind=decided, reason="extension", source=str(file_path))

    if suffix not in RECEPTOR_SUFFIXES:
        raise InvalidInputError(
            f"cannot tell what {file_path.name} is: "
            f"{file_path.suffix or 'no extension'!r} is not a format this application reads"
        )

    # Read it as a receptor first: that is the reading that can rule itself out
    # on the residue count, and the larger of the two cases in this application.
    receptor: Detection | None = None
    receptor_error: Exception | None = None
    try:
        preview = inspect_receptor(file_path)
        receptor = Detection(
            kind="receptor",
            reason="polymer residues",
            source=str(file_path),
            atoms=preview.atoms,
            residues=preview.residues,
            waters=len(preview.waters),
            chains=preview.chains,
        )
        if receptor.polymer_residues >= MIN_POLYMER_RESIDUES:
            return receptor
    except _UNREADABLE as exc:  # the reading does not fit this file at all
        receptor_error = exc

    if receptor is not None:
        # One residue is a small molecule in a protein-shaped file. Whether the
        # ligand reader accepts it is a separate question (a file carrying waters
        # is a small molecule that still cannot be parameterised), so the kind is
        # decided from the evidence already in hand.
        return Detection(
            kind="ligand",
            reason="small molecule",
            source=str(file_path),
            atoms=receptor.atoms,
            residues=receptor.residues,
            waters=receptor.waters,
            chains=receptor.chains,
        )

    # The receptor reading failed outright, so the ligand reading has the answer.
    try:
        ligand = inspect_ligand(file_path)
    except _UNREADABLE as exc:
        raise InvalidInputError(
            f"could not read {file_path.name} as a receptor or as a ligand: "
            f"{receptor_error or exc}"
        ) from exc

    return Detection(
        kind="ligand",
        reason="small molecule",
        source=str(file_path),
        atoms=ligand.atoms,
    )
