"""RDKit readers that never hand a filesystem path to RDKit.

RDKit's C++ file readers take a narrow ``std::string`` path, so on Windows any
path holding non-ASCII characters — a CJK user profile, or a data folder such
as ``D:\\数据\\配体.sdf`` — opens as garbage and every ligand read dies with
``OSError: File error: Bad input file <path>``.
The bytes are fine: Python, gemmi and this project's own parsers read the very
same file from the same directory. So the reader is at fault, not the data.

Reading here and parsing from a block or an in-memory stream keeps RDKit out of
path handling, which is what the PDBQT and SDF *text* paths in this package
already do. It also means an unopenable file surfaces as a domain error naming
the file instead of a bare ``OSError`` turning a request into a 500.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

from rdkit import Chem

from vinastudio.core.errors import InvalidInputError

__all__ = ["mol_from_file", "sdf_supplier"]


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InvalidInputError(f"cannot read {path}: {exc}") from exc


def sdf_supplier(
    path: Path, *, removeHs: bool = False, sanitize: bool = True
) -> Iterator[Chem.Mol | None]:
    """Records of an SD file in order; an unparsable record yields ``None``.

    ``ForwardSDMolSupplier`` reads a record at a time, so this shares the old
    ``SDMolSupplier``'s tolerance, minus its habit of refusing to open.
    """
    return Chem.ForwardSDMolSupplier(
        io.BytesIO(_read_bytes(path)), removeHs=removeHs, sanitize=sanitize
    )


def mol_from_file(
    path: Path, *, removeHs: bool = False, sanitize: bool = True
) -> Chem.Mol | None:
    """First molecule of an ``.sdf``/``.mol``/``.mol2``/``.pdb`` file.

    ``None`` means "no readable molecule" for every other suffix, and mirrors
    what RDKit's own readers returned for content they could not parse, so
    callers keep reporting their own ``no readable molecule in …`` message.
    """
    if path.suffix.lower() == ".sdf":
        records = sdf_supplier(path, removeHs=removeHs, sanitize=sanitize)
        return next((mol for mol in records if mol is not None), None)

    block = _read_bytes(path).decode("utf-8", errors="replace")
    if path.suffix.lower() == ".mol":
        return Chem.MolFromMolBlock(block, removeHs=removeHs, sanitize=sanitize)
    if path.suffix.lower() == ".mol2":
        return Chem.MolFromMol2Block(block, removeHs=removeHs, sanitize=sanitize)
    if path.suffix.lower() == ".pdb":
        return Chem.MolFromPDBBlock(block, removeHs=removeHs, sanitize=sanitize)
    return None
