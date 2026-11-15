"""Write a receptor + selected docking pose as one PDB complex.

The receptor is the prepared PDB (or a PDB converted from the prepared PDBQT);
the ligand comes from the pose SDF, which is the only artifact that carries bond
orders. The ligand is written as HETATM chain L, residue LIG, residue number 1,
and its bonds become CONECT records so viewers can show it without guessing.
"""

from __future__ import annotations

import contextlib
import io

from vinastudio.core.errors import InvalidInputError

LIGAND_CHAIN = "L"
LIGAND_RESNAME = "LIG"
LIGAND_RESSEQ = 1


def split_sdf_pose(text: str, pose: int = 1) -> str:
    """Return one SDF record (1-based), keeping the title line intact.

    The title line may be empty. Splitting on ``$$$$`` leaves the delimiter's
    newline at the front of every record after the first; remove exactly that
    one, never ``strip()`` the record, or an empty title is lost and the counts
    line shifts into the title column.
    """
    records: list[str] = []
    for index, record in enumerate(text.split("$$$$")):
        if not record.strip():
            continue
        if index > 0 and record.startswith("\n"):
            record = record[1:]
        records.append(record.rstrip("\n"))
    if pose < 1 or pose > len(records):
        raise InvalidInputError(f"pose {pose} is outside 1..{len(records)}")
    return records[pose - 1] + "\n"


def _ligand_molecule(pose_sdf: str):  # type: ignore[no-untyped-def]
    from rdkit import Chem

    supplier = Chem.ForwardSDMolSupplier(
        io.BytesIO(pose_sdf.encode("utf-8")), removeHs=False
    )
    molecule = next(iter(supplier), None)
    if molecule is None:
        raise InvalidInputError("could not parse the selected pose SDF")
    if molecule.GetNumConformers() == 0:
        raise InvalidInputError("the selected pose has no 3D coordinates")
    return molecule


def _atom_name(symbol: str, serial: int) -> str:
    return f"{symbol}{serial}"[:4]


def complex_pdb(
    receptor_pdb: str,
    pose_sdf: str,
    *,
    ligand_chain: str = LIGAND_CHAIN,
    ligand_resname: str = LIGAND_RESNAME,
    ligand_resseq: int = LIGAND_RESSEQ,
) -> str:
    """Combine a receptor PDB and one pose SDF into a complex PDB."""
    molecule = _ligand_molecule(pose_sdf)
    conformer = molecule.GetConformer()

    receptor_lines: list[str] = []
    max_serial = 0
    for line in receptor_pdb.splitlines():
        if line.startswith("END"):
            break
        if line.startswith(("ATOM", "HETATM", "TER", "CONECT", "REMARK", "TITLE")):
            receptor_lines.append(line)
            if line.startswith(("ATOM", "HETATM")):
                with contextlib.suppress(ValueError):
                    max_serial = max(max_serial, int(line[6:11]))

    ligand_serials: dict[int, int] = {}
    serial = max_serial
    ligand_lines: list[str] = []
    for index, atom in enumerate(molecule.GetAtoms(), start=1):
        serial += 1
        ligand_serials[index] = serial
        position = conformer.GetAtomPosition(index - 1)
        symbol = atom.GetSymbol()[:2]
        name = _atom_name(symbol, index)
        ligand_lines.append(
            f"HETATM{serial:5d} {name:<4} {ligand_resname:>3} "
            f"{ligand_chain[:1] or 'L'}{ligand_resseq:4d}    "
            f"{position.x:8.3f}{position.y:8.3f}{position.z:8.3f}"
            f"{1.0:6.2f}{0.0:6.2f}          {symbol:>2}  "
        )

    conect_lines: list[str] = []
    for bond in molecule.GetBonds():
        start = ligand_serials.get(bond.GetBeginAtomIdx() + 1)
        end = ligand_serials.get(bond.GetEndAtomIdx() + 1)
        if start is not None and end is not None:
            conect_lines.append(f"CONECT{start:5d}{end:5d}")

    lines = [
        f"REMARK    VinaStudio complex; ligand = {ligand_resname} chain {ligand_chain}",
        *receptor_lines,
        *ligand_lines,
        *conect_lines,
        "TER",
        "END",
    ]
    return "\n".join(lines) + "\n"
