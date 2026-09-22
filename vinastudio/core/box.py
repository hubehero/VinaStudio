"""The docking search box.

Vina's Python API takes a centre and three edge lengths and nothing else, so
everything else about the box has to be computed here. That includes the three
things the command-line tool does but the API does not expose:

* ``--autobox`` / ``--autobox_ligand`` / ``--autobox_extend`` — deriving the box
  from the coordinates of a ligand or a residue selection.
* ``--force_even_voxels`` — the parity rule that ``Vina.write_maps`` enforces.
* ``--config`` — reading and writing the ``config.txt`` format, so a session in
  this application and a run from the command line can exchange settings.

**Terminology, because it is easy to get wrong.** ``size`` is the full edge
length in Angstrom, not a half-extent. ``voxels`` is ``ceil(size / spacing)``.
The number of grid *points* along an axis is ``voxels + 1``, which is why
forcing an even voxel count also forces an odd number of grid points, and why
``write_maps`` refuses to run with an odd voxel count: AutoGrid's map format
stores the point count in a field that expects it to be odd.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from vinastudio.config import DEFAULT_SPACING
from vinastudio.core.chem.pdb_lines import (
    atom_records,
    coordinates,
    is_hydrogen_record,
    residue_key,
    scan_residues,
)
from vinastudio.core.errors import InvalidInputError

Point3 = tuple[float, float, float]

#: Keys understood in a Vina ``config.txt``. Anything else is preserved verbatim
#: by :func:`read_config` so a hand-edited file is not silently rewritten.
CONFIG_KEYS: Final[tuple[str, ...]] = (
    "center_x",
    "center_y",
    "center_z",
    "size_x",
    "size_y",
    "size_z",
    "spacing",
    "force_even_voxels",
)

_CONFIG_LINE_RE = re.compile(r"^\s*([a-z_]+)\s*=\s*(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Box:
    """A docking search box, in Vina's own terms."""

    center: Point3
    size: Point3
    spacing: float = DEFAULT_SPACING
    force_even_voxels: bool = False

    def __post_init__(self) -> None:
        self.validate()

    # -- validation --------------------------------------------------------
    def validate(self) -> None:
        """Check the invariants Vina enforces, with messages a user can act on."""
        if len(self.center) != 3:
            raise InvalidInputError("the box centre must be three coordinates in Angstrom")
        if len(self.size) != 3:
            raise InvalidInputError("the box size must be three edge lengths in Angstrom")
        if any(dimension <= 0 for dimension in self.size):
            raise InvalidInputError(
                f"every box edge must be positive, got {self.size[0]:g} x "
                f"{self.size[1]:g} x {self.size[2]:g} Angstrom"
            )
        if self.spacing <= 0:
            raise InvalidInputError(f"grid spacing must be positive, got {self.spacing:g}")
        if not all(math.isfinite(value) for value in (*self.center, *self.size, self.spacing)):
            raise InvalidInputError("the box contains a non-finite number")

    # -- derived quantities ------------------------------------------------
    @property
    def voxels(self) -> tuple[int, int, int]:
        """Voxel count per axis, after the parity rule Vina applies."""
        counts = [max(1, math.ceil(length / self.spacing)) for length in self.size]
        if self.force_even_voxels:
            counts = [count + (count % 2) for count in counts]
        return (counts[0], counts[1], counts[2])

    @property
    def grid_points(self) -> tuple[int, int, int]:
        """Grid points per axis: one more than the voxel count.

        ``write_maps`` compares this against an odd/even expectation, so the two
        properties are deliberately derived from one another.
        """
        return tuple(count + 1 for count in self.voxels)  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        """Enclosed volume in cubic Angstrom."""
        return round(self.size[0] * self.size[1] * self.size[2], 3)

    @property
    def can_write_maps(self) -> bool:
        """Whether ``Vina.write_maps`` would accept this box as it stands."""
        return all(count % 2 == 0 for count in self.voxels)

    @property
    def limits(self) -> tuple[Point3, Point3]:
        """Lower and upper corner, in Angstrom."""
        half = (self.size[0] / 2, self.size[1] / 2, self.size[2] / 2)
        lower = (
            round(self.center[0] - half[0], 3),
            round(self.center[1] - half[1], 3),
            round(self.center[2] - half[2], 3),
        )
        upper = (
            round(self.center[0] + half[0], 3),
            round(self.center[1] + half[1], 3),
            round(self.center[2] + half[2], 3),
        )
        return lower, upper

    def corners(self) -> list[Point3]:
        """The eight corners, ordered so consistent edge pairs can be drawn."""
        (x0, y0, z0), (x1, y1, z1) = self.limits
        return [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ]

    # -- editing -----------------------------------------------------------
    def with_center(self, center: Point3) -> Box:
        return replace(self, center=center)

    def with_size(self, size: Point3) -> Box:
        return replace(self, size=size)

    def moved_by(self, delta: Point3) -> Box:
        return replace(
            self,
            center=tuple(  # type: ignore[arg-type]
                round(self.center[axis] + delta[axis], 3) for axis in range(3)
            ),
        )

    def contains(self, point: Point3) -> bool:
        (x0, y0, z0), (x1, y1, z1) = self.limits
        return (
            x0 <= point[0] <= x1 and y0 <= point[1] <= y1 and z0 <= point[2] <= z1
        )

    def summary(self) -> dict[str, object]:
        """Compact description for the API and the UI."""
        return {
            "center": list(self.center),
            "size": list(self.size),
            "spacing": self.spacing,
            "forceEvenVoxels": self.force_even_voxels,
            "voxels": list(self.voxels),
            "gridPoints": list(self.grid_points),
            "volume": self.volume,
            "canWriteMaps": self.can_write_maps,
        }

    # -- config.txt --------------------------------------------------------
    def to_config(self) -> str:
        """Serialise to Vina's ``config.txt`` format."""
        lines = [f"center_{axis} = {self.center[index]:.3f}" for index, axis in enumerate("xyz")]
        lines += [f"size_{axis} = {self.size[index]:.3f}" for index, axis in enumerate("xyz")]
        lines.append(f"spacing = {self.spacing:g}")
        if self.force_even_voxels:
            lines.append("force_even_voxels = 1")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_config(cls, text: str) -> Box:
        """Parse the subset of ``config.txt`` that describes a box.

        Unknown keys (``receptor``, ``ligand``, ``exhaustiveness``, ...) are
        ignored rather than rejected: the same file legitimately describes a
        whole docking run.
        """
        values: dict[str, str] = {}
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = _CONFIG_LINE_RE.match(line)
            if match:
                values[match.group(1).lower()] = match.group(2)

        missing = [key for key in CONFIG_KEYS[:6] if key not in values]
        if missing:
            raise InvalidInputError(
                f"the configuration is missing {', '.join(missing)}; a box needs a "
                "centre and three edge lengths"
            )

        try:
            center = tuple(float(values[f"center_{axis}"]) for axis in "xyz")
            size = tuple(float(values[f"size_{axis}"]) for axis in "xyz")
            spacing = float(values.get("spacing", DEFAULT_SPACING))
        except ValueError as exc:
            raise InvalidInputError(f"the configuration has a non-numeric value: {exc}") from exc

        return cls(
            center=center,  # type: ignore[arg-type]
            size=size,  # type: ignore[arg-type]
            spacing=spacing,
            force_even_voxels=_as_bool(values.get("force_even_voxels")),
        )


def _as_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------
# autobox
# --------------------------------------------------------------------------


def bounds(points: list[Point3]) -> tuple[Point3, Point3]:
    """Axis-aligned bounding box of a set of coordinates."""
    if not points:
        raise InvalidInputError("no coordinates were given, so no box can be derived")
    xs, ys, zs = zip(*points, strict=True)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def autobox(
    points: list[Point3],
    *,
    extend: float = 0.0,
    spacing: float = DEFAULT_SPACING,
    force_even_voxels: bool = False,
) -> Box:
    """Derive a box that encloses ``points``.

    ``extend`` is added to **every side**, so each edge grows by twice that
    value. Stating it that way matters: "extend the box by 4 A" is ambiguous
    between a 4 A total growth and 4 A of margin per side, and the two differ by
    a factor of two in volume.
    """
    if extend < 0:
        raise InvalidInputError(f"extend must not be negative, got {extend:g}")

    lower, upper = bounds(points)
    center = tuple(round((lower[i] + upper[i]) / 2, 3) for i in range(3))
    size = tuple(round(upper[i] - lower[i] + 2 * extend, 3) for i in range(3))

    # A flat ligand (a planar aromatic, say) can have zero extent on one axis,
    # which is not a usable box; give it a floor of one grid step per axis.
    size = tuple(max(dimension, spacing) for dimension in size)

    return Box(
        center=center,  # type: ignore[arg-type]
        size=size,  # type: ignore[arg-type]
        spacing=spacing,
        force_even_voxels=force_even_voxels,
    )


def points_from_pdbqt(text: str, *, include_hydrogens: bool = False) -> list[Point3]:
    """Coordinates of the first pose in PDBQT content.

    PDBQT keeps only the polar hydrogens, but they are still hydrogens and are
    excluded by default for the same reason as everywhere else here.
    """
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    atoms = parse_pdbqt(text).first_pose.atoms
    points = [
        atom.coordinates
        for atom in atoms
        if include_hydrogens or not atom.is_polar_hydrogen
    ]
    if not points:
        raise InvalidInputError("the PDBQT contains no heavy atoms")
    return points


def points_from_pdb(
    text: str,
    residues: tuple[str, ...] = (),
    *,
    include_hydrogens: bool = False,
) -> list[Point3]:
    """Coordinates from PDB records, optionally limited to given residues.

    A residue is named ``chain:number`` (``A:315``), the same spelling Meeko uses
    in its messages, and an empty selection means every atom.
    """
    wanted = {name.strip() for name in residues if name.strip()}
    points: list[Point3] = []
    for line in atom_records(text):
        if wanted and residue_key(line) not in wanted:
            continue
        if not include_hydrogens and is_hydrogen_record(line):
            continue
        points.append(coordinates(line))

    if not points:
        if wanted:
            available = sorted(scan_residues(text))
            span = f" (it spans {available[0]} to {available[-1]})" if available else ""
            raise InvalidInputError(
                f"none of {', '.join(sorted(wanted))} are in the structure{span}"
            )
        raise InvalidInputError("the structure contains no atom records")
    return points


def points_from_rdkit_file(
    path: Path, *, include_hydrogens: bool = False
) -> list[Point3]:
    """Heavy-atom coordinates of the first molecule in an SD file or molfile.

    Hydrogens are read tolerantly (``sanitize=False``) because a structure that
    does not sanitise is still perfectly usable for defining a box, and RDKit
    only honours ``removeHs`` when sanitising.
    """
    from rdkit import Chem

    if path.suffix.lower() == ".sdf":
        molecules = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
        mol = next((candidate for candidate in molecules if candidate is not None), None)
    else:
        mol = Chem.MolFromMolFile(str(path), removeHs=False, sanitize=False)

    if mol is None:
        raise InvalidInputError(f"no readable molecule in {path.name}")
    if mol.GetNumConformers() == 0:
        raise InvalidInputError(f"{path.name} has no coordinates, so it cannot define a box")

    conformer = mol.GetConformer()
    indices = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if include_hydrogens or atom.GetAtomicNum() != 1
    ]
    if not indices:
        raise InvalidInputError(f"{path.name} contains no heavy atoms")

    return [
        (
            round(conformer.GetAtomPosition(index).x, 3),
            round(conformer.GetAtomPosition(index).y, 3),
            round(conformer.GetAtomPosition(index).z, 3),
        )
        for index in indices
    ]


def points_from_file(
    path: str | Path,
    residues: tuple[str, ...] = (),
    *,
    include_hydrogens: bool = False,
) -> list[Point3]:
    """Read coordinates from whichever supported format the path names."""
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix in {".sdf", ".mol"}:
        if residues:
            raise InvalidInputError(
                f"a residue selection cannot be applied to {suffix}: the format has "
                "no residue information"
            )
        return points_from_rdkit_file(file_path, include_hydrogens=include_hydrogens)
    if suffix == ".pdbqt":
        return points_from_pdbqt(
            file_path.read_text(encoding="utf-8", errors="replace"),
            include_hydrogens=include_hydrogens,
        )
    if suffix in {".pdb", ".ent"}:
        return points_from_pdb(
            file_path.read_text(encoding="utf-8", errors="replace"),
            residues,
            include_hydrogens=include_hydrogens,
        )
    raise InvalidInputError(
        f"cannot derive a box from {suffix or 'a file without an extension'}; "
        "expected .pdb, .ent, .pdbqt, .sdf or .mol"
    )


def autobox_from_file(
    path: str | Path,
    *,
    extend: float = 0.0,
    residues: tuple[str, ...] = (),
    spacing: float = DEFAULT_SPACING,
    force_even_voxels: bool = False,
    include_hydrogens: bool = False,
) -> tuple[Box, int]:
    """Derive a box from a file; returns the box and the number of points used."""
    points = points_from_file(path, residues, include_hydrogens=include_hydrogens)
    box = autobox(
        points,
        extend=extend,
        spacing=spacing,
        force_even_voxels=force_even_voxels,
    )
    return box, len(points)
