"""2D depiction coordinates for the interaction map (TASK-06).

LigPlot-style figures draw the ligand in 2D while the viewport keeps showing
the 3D pose: the two are *deliberately different geometries* (AGENTS.md), so
the 2D coordinates are always computed on a **copy** — ``Compute2DCoords``
rewrites the conformer it is handed and must never touch the 3D artifact the
contact analysis and the viewer describe.

For PDBQT input the molecule is restored through the same
``poses_to_sdf`` path pose export uses, so depiction and pose export describe
the same chemistry; bond orders are never guessed from PDBQT geometry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem

from vinastudio.core.chem.rdkit_io import mol_from_file
from vinastudio.core.errors import InvalidInputError

#: Inline text that is clearly an SDF/MOL block rather than a path.
_MOLBLOCK_MARKERS = ("V2000", "V3000", "M  END")
#: Inline text that is clearly a PDBQT record stream.
_PDBQT_STARTS = ("ATOM", "HETATM", "REMARK", "ROOT", "BRANCH", "TORSDOF", "MODEL")


def depict_2d(source: Chem.Mol | str | Path) -> dict[str, Any]:
    """Normalized 2D coordinates for one molecule.

    ``source`` may be an RDKit mol, an SDF/MOL block or file path, or a PDBQT
    text/path (restored via ``poses_to_sdf``'s SMILES path).

    Returns ``{"atoms": [...], "bonds": [...]}``. Every atom carries its
    unit-square position ``(x, y)`` — the longer axis spans ``[0, 1]``, the
    aspect ratio is kept, everything stays inside the square — plus the
    original 3D coordinates ``(x3, y3, z3)`` (``None`` when the source had no
    conformer). The 3D triple exists so callers can match a contact row, which
    knows only 3D positions, to the right 2D atom: PDBQT restoration adds
    hydrogens, so *indices* do not line up with the input file, while
    coordinates are preserved exactly.

    Raises ``InvalidInputError`` when the molecule cannot be loaded or laid
    out; callers that treat depiction as optional should catch
    ``VinaStudioError``.
    """
    mol = _load_mol(source)

    # Snapshot the 3D coordinates before the copy is flattened to the plane.
    has_3d = mol.GetNumConformers() > 0
    conf3d = mol.GetConformer() if has_3d else None

    work = Chem.Mol(mol)  # the copy is the whole point: 2D must not rewrite 3D
    try:
        AllChem.Compute2DCoords(work)
    except Exception as exc:
        raise InvalidInputError(f"could not compute 2D coordinates: {exc}") from exc

    conf = work.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(work.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(work.GetNumAtoms())]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span = max(max_x - min_x, max_y - min_y)
    if span <= 1e-9:
        # A single atom (or a degenerate layout): pin to the centre.
        scale, offset_x, offset_y = 0.0, 0.5, 0.5
    else:
        scale = 1.0 / span
        offset_x = (1.0 - (max_x - min_x) * scale) / 2.0
        offset_y = (1.0 - (max_y - min_y) * scale) / 2.0

    atoms: list[dict[str, Any]] = []
    for atom in work.GetAtoms():
        idx = atom.GetIdx()
        pos = conf.GetAtomPosition(idx)
        pos3 = conf3d.GetAtomPosition(idx) if conf3d is not None else None
        atoms.append({
            "idx": idx,
            "x": round((pos.x - min_x) * scale + offset_x, 4),
            "y": round((pos.y - min_y) * scale + offset_y, 4),
            "x3": round(pos3.x, 3) if pos3 is not None else None,
            "y3": round(pos3.y, 3) if pos3 is not None else None,
            "z3": round(pos3.z, 3) if pos3 is not None else None,
            "symbol": atom.GetSymbol(),
            "charge": atom.GetFormalCharge(),
            "aromatic": bool(atom.GetIsAromatic()),
        })

    bonds = [
        {
            "a1": bond.GetBeginAtomIdx(),
            "a2": bond.GetEndAtomIdx(),
            "order": bond.GetBondTypeAsDouble(),
            "aromatic": bool(bond.GetIsAromatic()),
        }
        for bond in work.GetBonds()
    ]
    return {"atoms": atoms, "bonds": bonds}


def _load_mol(source: Chem.Mol | str | Path) -> Chem.Mol:
    """Resolve *source* into an RDKit mol carrying its 3D coordinates."""
    if isinstance(source, Chem.Mol):
        return source
    if isinstance(source, Path):
        return _mol_from_path(source)
    if "\n" in source:
        if any(marker in source for marker in _MOLBLOCK_MARKERS):
            return _mol_from_molblock(source)
        return _mol_from_pdbqt(source)
    if source.startswith(_PDBQT_STARTS):
        # A single-line PDBQT fragment (tests build these).
        return _mol_from_pdbqt(source)
    return _mol_from_path(Path(source))


def _mol_from_path(path: Path) -> Chem.Mol:
    if not path.exists():
        raise InvalidInputError(f"cannot read ligand file {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdbqt":
        return _mol_from_pdbqt(path.read_text(encoding="utf-8", errors="replace"))
    if suffix in (".sdf", ".mol"):
        mol = mol_from_file(path, removeHs=False)
        if mol is None:
            raise InvalidInputError(f"RDKit could not parse {path}")
        return mol
    raise InvalidInputError(
        f"unsupported depiction source {path}: expected .sdf, .mol or .pdbqt"
    )


def _mol_from_molblock(text: str) -> Chem.Mol:
    record = text.split("$$$$")[0]
    mol = Chem.MolFromMolBlock(record, removeHs=False)
    if mol is None:
        raise InvalidInputError("RDKit could not parse the ligand mol block")
    return mol


def _mol_from_pdbqt(text: str) -> Chem.Mol:
    """Restore chemistry through the shared pose-export path."""
    from vinastudio.core.chem.export import poses_to_sdf

    sdf = poses_to_sdf(text)  # raises PreparationError when SMILES is missing
    record = sdf.sdf.split("$$$$")[0]
    mol = Chem.MolFromMolBlock(record, removeHs=False)
    if mol is None:
        raise InvalidInputError("pose export produced no usable ligand molecule")
    return mol
