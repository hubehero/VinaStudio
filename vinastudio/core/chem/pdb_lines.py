"""Reading PDB records.

The PDB format addresses its fields by column, and those offsets are needed by
more than one part of the pipeline — receptor preparation groups residues, and
the search box needs the coordinates of a residue selection. Keeping the offsets
in one place means they cannot drift apart, and it keeps a private helper from
having to be imported across modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from vinastudio.core.errors import InvalidInputError

#: Residue names treated as solvent rather than as part of a structure.
WATER_RESIDUES: Final[frozenset[str]] = frozenset(
    {"HOH", "WAT", "DOD", "H2O", "TIP", "TIP3", "SOL"}
)

# Column slices, 0-indexed, per the PDB specification.
_RESIDUE_NAME: Final = slice(17, 20)
_CHAIN: Final = slice(21, 22)
_RESIDUE_NUMBER: Final = slice(22, 27)
_X: Final = slice(30, 38)
_Y: Final = slice(38, 46)
_Z: Final = slice(46, 54)


@dataclass(slots=True)
class ResidueSummary:
    """What a residue looks like in a file, before any chemistry is applied."""

    key: str
    name: str
    atoms: int
    hetero: bool

    @property
    def is_water(self) -> bool:
        return self.name.upper() in WATER_RESIDUES


def residue_key(line: str) -> str:
    """Residue identifier for a PDB record, as ``chain:number``.

    The number keeps any insertion code, so ``A:42B`` and ``A:42`` stay
    distinct. Meeko uses the same spelling in its error messages, which is what
    makes those messages actionable.
    """
    return f"{line[_CHAIN].strip()}:{line[_RESIDUE_NUMBER].strip()}"


def coordinates(line: str) -> tuple[float, float, float]:
    """Cartesian coordinates of an ``ATOM``/``HETATM`` record."""
    try:
        return (float(line[_X]), float(line[_Y]), float(line[_Z]))
    except ValueError as exc:
        raise InvalidInputError(
            f"could not read coordinates from this record: {line[:54]!r}"
        ) from exc


def is_hydrogen_record(line: str) -> bool:
    """Whether a record describes a hydrogen.

    The element column is authoritative when present. Some writers leave it
    blank, which is why the atom name is used as a fallback: PDB names put the
    element first, and hydrogen names always start with ``H`` (or ``1H``/``2H``
    for the amide protons written by some tools).
    """
    element = line[76:78].strip()
    if element:
        return element.upper() == "H"
    name = line[12:16].strip().lstrip("0123456789")
    return name.upper().startswith("H")


def scan_residues(text: str) -> dict[str, ResidueSummary]:
    """Group ``ATOM``/``HETATM`` records by residue, in file order."""
    collected: dict[str, ResidueSummary] = {}
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        key = residue_key(line)
        summary = collected.get(key)
        if summary is None:
            summary = ResidueSummary(
                key=key,
                name=line[_RESIDUE_NAME].strip(),
                atoms=0,
                hetero=line.startswith("HETATM"),
            )
            collected[key] = summary
        summary.atoms += 1
        if line.startswith("ATOM"):
            # A residue with any polymer record is not a hetero group.
            summary.hetero = False
    return collected


def split_solvent(
    residues: dict[str, ResidueSummary],
) -> tuple[list[str], list[str]]:
    """Split residues into (waters, non-water hetero groups), both sorted."""
    waters = sorted(key for key, entry in residues.items() if entry.is_water)
    hetero = sorted(
        key for key, entry in residues.items() if entry.hetero and not entry.is_water
    )
    return waters, hetero


def atom_records(text: str) -> list[str]:
    """The ``ATOM``/``HETATM`` lines of a structure, in order."""
    return [
        line for line in text.splitlines() if line.startswith(("ATOM", "HETATM"))
    ]


def group_runs(keys: list[str]) -> list[tuple[str, int, int]]:
    """Contiguous runs of equal keys, as (key, start, end) in item coordinates."""
    runs: list[tuple[str, int, int]] = []
    start = 0
    for position in range(1, len(keys) + 1):
        if position == len(keys) or keys[position] != keys[start]:
            runs.append((keys[start], start, position))
            start = position
    return runs
