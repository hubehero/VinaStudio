"""A parser for the PDBQT dialect AutoDock uses.

PDBQT is a lossy PDB extension: it adds partial charges and AutoDock atom types
and drops bond orders and non-polar hydrogens. Read it to learn *what* is in a
pose and *where* the atoms are, never to reconstruct chemistry — bond orders
have to come from the SMILES Meeko records in the header.

The torsion tree (``ROOT``/``BRANCH``/``ENDBRANCH``) is preserved because the
number of branch records is the number of rotatable bonds, which is exactly the
number of degrees of freedom docking searches over.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from vinastudio.core.chem.autodock_types import element_for

# PDBQT is column-based; these slices match the PDB specification with the
# additional charge/type columns AutoDock appends.
_COLUMNS: Final = {
    "serial": slice(6, 11),
    "name": slice(12, 16),
    "resname": slice(17, 20),
    "chain": slice(21, 22),
    "resid": slice(22, 26),
    "insertion": slice(26, 27),
    "x": slice(30, 38),
    "y": slice(38, 46),
    "z": slice(46, 54),
    "occupancy": slice(54, 60),
    "bfactor": slice(60, 66),
    "charge": slice(66, 76),
    "atom_type": slice(76, 79),
}

_VINA_RESULT_RE: Final = re.compile(
    r"^REMARK\s+VINA\s+RESULT:\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)"
)
#: `REMARK SMILES <smiles>` carries exactly one token, which is what separates it
#: from the multi-token `REMARK SMILES IDX ...` line.
_SMILES_RE: Final = re.compile(r"^REMARK\s+SMILES\s+(\S+)\s*$")
_SMILES_IDX_RE: Final = re.compile(r"^REMARK\s+SMILES\s+IDX\s+(.+)$")
_H_PARENT_RE: Final = re.compile(r"^REMARK\s+H\s+PARENT\s+(.+)$")
_TORSDOF_RE: Final = re.compile(r"^TORSDOF\s+(\d+)")
_BRANCH_RE: Final = re.compile(r"^BRANCH\s+(\d+)\s+(\d+)")


class PdbqtError(ValueError):
    """Raised when a file looks like PDBQT but cannot be understood."""


@dataclass(frozen=True, slots=True)
class PdbqtAtom:
    serial: int
    name: str
    resname: str
    chain: str
    resid: int
    x: float
    y: float
    z: float
    charge: float
    atom_type: str
    occupancy: float = 1.0
    bfactor: float = 0.0
    insertion: str = ""

    @property
    def element(self) -> str:
        """Chemical element.

        The AutoDock type decides it: an atom name beginning ``NA`` is an
        acceptor nitrogen, not sodium, and type ``A`` is aromatic carbon.
        """
        return element_for(self.name, self.atom_type)

    @property
    def is_polar_hydrogen(self) -> bool:
        return self.atom_type in {"H", "HD", "HS"}

    @property
    def coordinates(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True, slots=True)
class TorsionBranch:
    """One rotatable bond, recorded as the parent/child atom serial pair."""

    parent_serial: int
    child_serial: int


@dataclass(slots=True)
class PdbqtPose:
    """A single docking result (one ``MODEL`` in the output file)."""

    index: int
    atoms: list[PdbqtAtom] = field(default_factory=list)
    branches: list[TorsionBranch] = field(default_factory=list)
    torsdof: int | None = None
    energy: float | None = None
    rmsd_lower_bound: float | None = None
    rmsd_upper_bound: float | None = None

    @property
    def n_atoms(self) -> int:
        return len(self.atoms)

    @property
    def rotatable_bonds(self) -> int:
        """Number of BRANCH records, i.e. torsional degrees of freedom."""
        return len(self.branches)

    @property
    def atom_types(self) -> Counter[str]:
        return Counter(atom.atom_type for atom in self.atoms)

    @property
    def total_charge(self) -> float:
        return round(sum(atom.charge for atom in self.atoms), 3)

    def coordinates(self) -> list[tuple[float, float, float]]:
        return [atom.coordinates for atom in self.atoms]

    @property
    def centroid(self) -> tuple[float, float, float]:
        if not self.atoms:
            raise PdbqtError("pose contains no atoms")
        n = len(self.atoms)
        return (
            round(sum(a.x for a in self.atoms) / n, 3),
            round(sum(a.y for a in self.atoms) / n, 3),
            round(sum(a.z for a in self.atoms) / n, 3),
        )


@dataclass(slots=True)
class PdbqtDocument:
    """Everything worth knowing about a PDBQT file or string."""

    poses: list[PdbqtPose] = field(default_factory=list)
    smiles: str | None = None
    """SMILES from ``REMARK SMILES``; the only source of bond orders."""
    smiles_index_map: tuple[int, ...] = ()
    """Flattened (pdbqt_serial, smiles_atom_index) pairs."""
    hydrogen_parents: tuple[int, ...] = ()
    """Flattened (hydrogen_serial, parent_serial) pairs."""
    source: str | None = None

    @property
    def n_poses(self) -> int:
        return len(self.poses)

    @property
    def is_multi_model(self) -> bool:
        return len(self.poses) > 1

    @property
    def first_pose(self) -> PdbqtPose:
        if not self.poses:
            raise PdbqtError("document contains no poses")
        return self.poses[0]

    @property
    def rotatable_bonds(self) -> int:
        return self.first_pose.rotatable_bonds if self.poses else 0

    @property
    def energies(self) -> list[float | None]:
        return [pose.energy for pose in self.poses]

    def best_pose(self) -> PdbqtPose | None:
        """Pose with the lowest (most favourable) affinity, or ``None``."""
        scored = [pose for pose in self.poses if pose.energy is not None]
        return min(scored, key=lambda pose: pose.energy or 0.0) if scored else None

    def summary(self) -> dict[str, object]:
        """Compact description used by the API and the UI."""
        pose = self.first_pose if self.poses else None
        return {
            "poses": self.n_poses,
            "atoms": pose.n_atoms if pose else 0,
            "rotatableBonds": self.rotatable_bonds,
            "torsdof": pose.torsdof if pose else None,
            "atomTypes": dict(pose.atom_types) if pose else {},
            "totalCharge": pose.total_charge if pose else 0.0,
            "smiles": self.smiles,
            "energies": [e for e in self.energies if e is not None],
        }


def _as_float(raw: str, default: float = 0.0) -> float:
    text = raw.strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _as_int(raw: str, default: int = 0) -> int:
    text = raw.strip()
    if not text:
        return default
    digits = re.match(r"-?\d+", text)
    return int(digits.group()) if digits else default


def _parse_atom(line: str) -> PdbqtAtom:
    def col(key: str) -> str:
        return line[_COLUMNS[key]]

    return PdbqtAtom(
        serial=_as_int(col("serial")),
        name=col("name").strip(),
        resname=col("resname").strip(),
        chain=col("chain").strip(),
        resid=_as_int(col("resid")),
        x=_as_float(col("x")),
        y=_as_float(col("y")),
        z=_as_float(col("z")),
        occupancy=_as_float(col("occupancy"), 1.0),
        bfactor=_as_float(col("bfactor")),
        charge=_as_float(col("charge")),
        atom_type=col("atom_type").strip(),
        insertion=col("insertion").strip(),
    )


def parse_pdbqt(text: str, *, source: str | None = None) -> PdbqtDocument:
    """Parse PDBQT content.

    Accepts both a single pose (no ``MODEL`` records, as written for a ligand
    input) and a multi-model docking output.
    """
    document = PdbqtDocument(source=source)
    pose = PdbqtPose(index=1)
    seen_model = False
    smiles_idx: list[int] = []
    h_parents: list[int] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        if line.startswith("MODEL"):
            if seen_model and pose.atoms:
                document.poses.append(pose)
                pose = PdbqtPose(index=len(document.poses) + 1)
            seen_model = True
            continue
        if line.startswith("ENDMDL"):
            if pose.atoms:
                document.poses.append(pose)
            pose = PdbqtPose(index=len(document.poses) + 1)
            continue

        if line.startswith("REMARK"):
            if match := _VINA_RESULT_RE.match(line):
                pose.energy = float(match.group(1))
                pose.rmsd_lower_bound = float(match.group(2))
                pose.rmsd_upper_bound = float(match.group(3))
            elif match := _SMILES_IDX_RE.match(line):
                smiles_idx.extend(_as_int(token) for token in match.group(1).split())
            elif match := _H_PARENT_RE.match(line):
                h_parents.extend(_as_int(token) for token in match.group(1).split())
            elif match := _SMILES_RE.match(line):
                document.smiles = match.group(1)
            continue

        if line.startswith(("ATOM", "HETATM")):
            pose.atoms.append(_parse_atom(line))
            continue

        if line.startswith("ROOT") or line.startswith("ENDROOT"):
            continue
        if match := _BRANCH_RE.match(line):
            pose.branches.append(
                TorsionBranch(
                    parent_serial=int(match.group(1)),
                    child_serial=int(match.group(2)),
                )
            )
            continue
        if line.startswith("ENDBRANCH"):
            continue
        if match := _TORSDOF_RE.match(line):
            pose.torsdof = int(match.group(1))
            continue
        if line.startswith(("TER", "END", "MASTER", "COMPND", "AUTHOR", "CRYST1")):
            continue
        # Anything else (TITLE, HEADER, ...) carries no pose information.

    if pose.atoms:
        document.poses.append(pose)

    if not document.poses:
        raise PdbqtError("no ATOM records found; this does not look like PDBQT")

    document.smiles_index_map = tuple(smiles_idx)
    document.hydrogen_parents = tuple(h_parents)
    return document


def read_pdbqt(path: str | Path) -> PdbqtDocument:
    """Parse a PDBQT file from disk."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PdbqtError(f"cannot read {file_path}: {exc}") from exc
    return parse_pdbqt(text, source=str(file_path))
