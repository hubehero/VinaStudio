"""Format conversion for docking results and receptors.

Why this exists at all: **3Dmol.js cannot read PDBQT**, and PDBQT has no bond
orders, so a pose cannot be rendered from it directly. Meeko writes the input
SMILES into every PDBQT header, and ``RDKitMolCreate`` re-instantiates an RDKit
molecule from that SMILES before copying the docked coordinates onto it. The
result is an SDF with the original bond orders and formal charges — the only
scientifically defensible way to go from a pose back to a molecule.

Receptors are different: a cartoon rendering only needs residue and element
records, so trimming the AutoDock charge/type columns off a receptor PDBQT
yields a perfectly adequate PDB. No bond perception is involved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from vinastudio.core.chem.autodock_types import element_for
from vinastudio.core.chem.pdbqt import PdbqtDocument, parse_pdbqt, read_pdbqt
from vinastudio.core.errors import InvalidInputError, PreparationError

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PoseSdf:
    """SDF export of every pose in a docking output."""

    sdf: str
    n_poses: int
    atoms: int
    energies: list[float] = field(default_factory=list)
    """Affinity per pose, in file order; missing affinities are omitted."""
    titles: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


#: Element symbols two characters wide, which PDB left-aligns in the name field.
_TWO_CHARACTER_ELEMENTS = frozenset({"Cl", "Br", "Si", "Mg", "Mn", "Zn", "Ca", "Fe", "Na"})


def pdbqt_to_pdb(
    source: str | Path | PdbqtDocument,
    *,
    title: str | None = None,
    model: int = 0,
) -> str:
    """Rewrite PDBQT atom records as standard PDB, for 3D rendering.

    Only the AutoDock charge and atom-type columns are dropped; coordinates,
    occupancies and residue information are carried over unchanged.
    """
    document = _as_document(source)
    if model < 0 or model >= document.n_poses:
        raise InvalidInputError(
            f"pose {model + 1} does not exist; the file holds {document.n_poses}"
        )
    pose = document.poses[model]

    lines: list[str] = []
    if title:
        lines.append(f"TITLE     {title}")
    if document.smiles:
        # Kept as a remark so the chemistry travels with the coordinates.
        lines.append(f"REMARK    SMILES {document.smiles}")
    if pose.energy is not None:
        lines.append(
            f"REMARK    VINA RESULT: {pose.energy:8.3f}  "
            f"{pose.rmsd_lower_bound or 0.0:8.3f}  {pose.rmsd_upper_bound or 0.0:8.3f}"
        )

    for atom in pose.atoms:
        element = element_for(atom.name, atom.atom_type)
        # PDB convention: a two-character element symbol is left-aligned in the
        # four-character name field, a one-character symbol is right-aligned.
        name = f"{atom.name:<4}" if element in _TWO_CHARACTER_ELEMENTS else f"{atom.name:>4}"
        lines.append(
            f"ATOM  {atom.serial:5d} {name} "
            f"{atom.resname:>3} "
            f"{atom.chain[:1] or ' '}"
            f"{atom.resid:4d}{atom.insertion[:1]:1}"
            f"   {atom.x:8.3f}{atom.y:8.3f}{atom.z:8.3f}"
            f"{atom.occupancy:6.2f}{atom.bfactor:6.2f}"
            f"          {element:>2}  "
        )

    lines.append("TER")
    lines.append("END")
    return "\n".join(lines) + "\n"


def _as_document(source: str | Path | PdbqtDocument) -> PdbqtDocument:
    if isinstance(source, PdbqtDocument):
        return source
    if isinstance(source, Path):
        return read_pdbqt(source)
    # A path-like string that names an existing file is read; anything else is
    # treated as PDBQT content.
    candidate = Path(source)
    if "\n" not in source and candidate.suffix.lower() == ".pdbqt":
        return read_pdbqt(candidate)
    return parse_pdbqt(source)


def _sd_record(mol, conformer_id: int, properties: dict[str, object]) -> str:  # type: ignore[no-untyped-def]
    """Serialise one conformer as an SD record with data fields."""
    from rdkit import Chem

    block = Chem.MolToMolBlock(mol, confId=conformer_id).rstrip("\n")
    lines = [block]
    for key, value in properties.items():
        lines.append(f">  <{key}>")
        lines.append(str(value))
        lines.append("")
    lines.append("$$$$")
    return "\n".join(lines) + "\n"


def poses_to_sdf(
    source: str | Path | PdbqtDocument,
    *,
    title_prefix: str = "pose",
) -> PoseSdf:
    """Convert every pose in a docking result into SDF.

    Poses come from the PDBQT (which model each one is) and the chemistry from
    the SMILES in its header, so bond orders and formal charges are restored
    rather than guessed.
    """
    from meeko import PDBQTMolecule, RDKitMolCreate

    document = _as_document(source)
    text = _pdbqt_text(source, document)

    try:
        pdbqt_mol = PDBQTMolecule(text, skip_typing=True)
        molecules = RDKitMolCreate.from_pdbqt_mol(pdbqt_mol)
    except Exception as exc:
        raise PreparationError(f"could not convert poses to SDF: {exc}") from exc

    if not molecules or molecules[0] is None:
        raise PreparationError(
            "Meeko produced no molecule from the docking output; without the "
            "REMARK SMILES line the bond orders cannot be restored, and guessing "
            "them from PDBQT distances is not reliable"
        )

    warnings: list[str] = []
    if len(molecules) > 1:
        warnings.append(
            f"the file holds {len(molecules)} ligands; SDF export covers the first, "
            "with one record per pose"
        )

    mol = molecules[0]
    n_conformers = mol.GetNumConformers()
    if n_conformers != document.n_poses:
        warnings.append(
            f"{document.n_poses} poses in the PDBQT but {n_conformers} conformers from "
            "Meeko; the export follows the conformers"
        )

    records: list[str] = []
    energies: list[float] = []
    titles: list[str] = []
    for index in range(n_conformers):
        pose = document.poses[index] if index < document.n_poses else None
        title = f"{title_prefix}_{index + 1}"
        titles.append(title)

        properties: dict[str, object] = {"pose": index + 1}
        if pose is not None and pose.energy is not None:
            energies.append(pose.energy)
            properties["affinity_kcal_per_mol"] = round(pose.energy, 3)
            properties["rmsd_lb"] = round(pose.rmsd_lower_bound or 0.0, 3)
            properties["rmsd_ub"] = round(pose.rmsd_upper_bound or 0.0, 3)

        # Each conformer is written under its own title, so downstream tools see
        # one named pose per record instead of four copies of the input name.
        mol.SetProp("_Name", title)
        records.append(_sd_record(mol, index, properties))

    if not energies:
        warnings.append("no VINA RESULT remarks found; the SDF carries no affinities")

    return PoseSdf(
        sdf="".join(records),
        n_poses=n_conformers,
        atoms=mol.GetNumAtoms(),
        energies=energies,
        titles=titles,
        warnings=warnings,
    )


def _pdbqt_text(source: str | Path | PdbqtDocument, document: PdbqtDocument) -> str:
    """Recover the original PDBQT text, or rebuild an equivalent one."""
    if isinstance(source, PdbqtDocument):
        if source.source and Path(source.source).is_file():
            return Path(source.source).read_text(encoding="utf-8", errors="replace")
        raise InvalidInputError(
            "a parsed document without its source file cannot be converted; pass the "
            "PDBQT text or a path instead"
        )
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8", errors="replace")
    if "\n" not in source and Path(source).suffix.lower() == ".pdbqt":
        return Path(source).read_text(encoding="utf-8", errors="replace")
    return source


def write_text(path: str | Path, content: str) -> Path:
    """Write text atomically, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
