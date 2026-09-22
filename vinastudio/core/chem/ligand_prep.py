"""Ligand preparation: MOL/SDF/MOL2/PDB -> PDBQT through Meeko.

Three separate transformations hide behind "convert to PDBQT", and each changes
the scientific result, so each is explicit and reported:

1. **Protonation** — Meeko refuses a molecule with implicit hydrogens. They are
   added, placed from the existing geometry when 3D coordinates are present, and
   the count is reported. This is not optional, so it is not an option.
2. **3D embedding** — a 2D molfile has no coordinates at all. They are generated
   with ETKDGv3 and relaxed with a force field, because a raw embedding can hold
   steric clashes that would distort the docking score.
3. **Parameterisation** — Meeko assigns AutoDock atom types, Gasteiger charges
   and the rotatable-bond tree, and writes the PDBQT.

The output is smaller than the input by design: PDBQT records heavy atoms and
**polar** hydrogens only, dropping the non-polar ones. The report states the
drop, because "69 atoms became 40" looks like data loss otherwise.

The written PDBQT is re-parsed with this project's own parser so the report
quotes Meeko's actual output (atom count, branch count, net charge) rather than
what we hoped it produced.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, rdMolDescriptors

from vinastudio.core.chem.formats import detect_format, is_supported
from vinastudio.core.chem.pdbqt import PdbqtError, parse_pdbqt
from vinastudio.core.errors import (
    InvalidInputError,
    PreparationError,
    UnsupportedFormatError,
    brief_error,
)

log = logging.getLogger(__name__)

#: Route RDKit's diagnostics into Python logging so parse failures can quote the
#: real reason instead of guessing.
rdBase.LogToPythonLogger()
_RDKIT_LOGGER = logging.getLogger("rdkit")

#: Formats this module can parameterise. A PDBQT is already prepared.
PREPARABLE_SUFFIXES = (".mol", ".sdf", ".mol2", ".pdb")

DEFAULT_EMBED_SEED = 0xF00D


@dataclass(frozen=True, slots=True)
class LigandPrepOptions:
    """User-facing choices for ligand preparation.

    Adding hydrogens and generating 3D coordinates are *not* options: Meeko
    refuses a molecule with implicit hydrogens, and there is nothing to dock
    without coordinates. Both steps always run when needed and are reported
    instead, so the interface can show what changed.

    What stays configurable is the force-field cleanup and Meeko's own
    chemistry decisions.
    """

    optimise_geometry: bool = True
    embed_seed: int = DEFAULT_EMBED_SEED

    # Passed straight to Meeko.
    rigid_macrocycles: bool = False
    flexible_amides: bool = False
    hydrate: bool = False
    double_bond_penalty: float = 50.0


@dataclass(slots=True)
class LigandReport:
    """What actually happened, in a shape the interface can display."""

    source: str
    input_format: str
    input_atoms: int
    hydrogens_added: int
    conformer_generated: bool
    geometry_optimised: bool
    output_atoms: int
    output_polar_hydrogens: int
    nonpolar_hydrogens_removed: int
    rotatable_bonds: int
    total_charge: float
    atom_types: dict[str, int]
    smiles: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LigandPreparation:
    """Result of a successful preparation."""

    pdbqt: str
    """PDBQT text, ready for ``Vina.set_ligand_from_string`` or a file."""
    sdf: str
    """Prepared molecule as SDF, for 3D preview (PDBQT itself is unrenderable)."""
    report: LigandReport


@dataclass(slots=True)
class LigandInspection:
    """Cheap pre-flight view of a ligand file, used by the conversion wizard."""

    source: str
    input_format: str
    preparable: bool
    atoms: int
    hydrogens: int
    has_3d_coordinates: bool
    rotatable_bonds: int
    molecular_formula: str | None
    molecular_weight: float | None
    smiles: str | None
    records: int
    notes: list[str] = field(default_factory=list)


@contextmanager
def _captured_rdkit_messages() -> Iterator[list[str]]:
    """Collect RDKit's own error text emitted while parsing or sanitising."""
    messages: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            text = record.getMessage().strip()
            if text:
                messages.append(text)

    handler = _Collector(level=logging.DEBUG)
    _RDKIT_LOGGER.addHandler(handler)
    previous_level = _RDKIT_LOGGER.level
    _RDKIT_LOGGER.setLevel(logging.DEBUG)
    try:
        yield messages
    finally:
        _RDKIT_LOGGER.removeHandler(handler)
        _RDKIT_LOGGER.setLevel(previous_level)


def _explain(messages: list[str], fallback: str) -> str:
    """The one line worth showing the user for a failed read or parameterisation."""
    return brief_error(messages[-1] if messages else fallback)


def read_mol(path: Path) -> tuple[Chem.Mol, int]:
    """Read the first molecule from a ligand file.

    Returns the molecule and the number of records found, so a multi-molecule
    file can be flagged rather than silently truncated.
    """
    suffix = path.suffix.lower()

    if suffix == ".sdf":
        with _captured_rdkit_messages() as messages:
            supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=True)
            first: Chem.Mol | None = None
            total = 0
            for mol in supplier:
                total += 1
                if first is None:
                    first = mol
        if first is None:
            raise InvalidInputError(
                f"no readable molecule in {path.name}: {_explain(messages, 'RDKit returned nothing')}"
            )
        return first, total

    with _captured_rdkit_messages() as messages:
        if suffix == ".mol":
            mol = Chem.MolFromMolFile(str(path), removeHs=False, sanitize=True)
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False, sanitize=True)
        elif suffix == ".pdb":
            mol = Chem.MolFromPDBFile(str(path), removeHs=False, sanitize=True)
        else:
            raise UnsupportedFormatError(f"cannot parameterise a {suffix} file")

    if mol is None:
        raise InvalidInputError(
            f"could not read {path.name}: "
            f"{_explain(messages, 'the file is not valid for its extension')}"
        )
    return mol, 1


def _has_3d(mol: Chem.Mol) -> bool:
    if mol.GetNumConformers() == 0:
        return False
    return bool(mol.GetConformer().Is3D())


def _count_attached_hydrogens(mol: Chem.Mol) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 1)


def _count_implicit_hydrogens(mol: Chem.Mol) -> int:
    return sum(atom.GetTotalNumHs() for atom in mol.GetAtoms())


def _canonical_smiles(mol: Chem.Mol) -> str | None:
    """Heavy-atom canonical SMILES.

    Hydrogens are stripped first: the molecule is read with ``removeHs=False``,
    so ``MolToSmiles`` would otherwise emit an explicit ``[H]`` for every one of
    them. That is unreadable and not the form anyone compares against.
    """
    try:
        return Chem.MolToSmiles(Chem.RemoveHs(mol))
    except Exception as exc:  # noqa: BLE001 - sanitisation can fail on odd input
        log.warning("could not canonicalise SMILES without hydrogens: %s", exc)
        try:
            return Chem.MolToSmiles(mol)
        except Exception:  # noqa: BLE001
            return None


def inspect_ligand(path: str | Path) -> LigandInspection:
    """Describe a ligand file without parameterising it."""
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")

    if not is_supported(file_path, "ligand"):
        raise UnsupportedFormatError(
            f"unsupported ligand extension {file_path.suffix!r}; "
            "expected one of .mol .sdf .mol2 .pdb .pdbqt"
        )

    fmt = detect_format(file_path) or file_path.suffix.lstrip(".")
    if fmt == "pdbqt":
        from vinastudio.core.chem.pdbqt import read_pdbqt

        document = read_pdbqt(file_path)
        pose = document.first_pose
        return LigandInspection(
            source=str(file_path),
            input_format=fmt,
            preparable=False,
            atoms=pose.n_atoms,
            hydrogens=sum(1 for atom in pose.atoms if atom.is_polar_hydrogen),
            has_3d_coordinates=True,
            rotatable_bonds=document.rotatable_bonds,
            molecular_formula=None,
            molecular_weight=None,
            smiles=document.smiles,
            records=document.n_poses,
            notes=[
                "already in PDBQT (AutoDock's polar-hydrogen-only representation); "
                "it is docked as-is, not re-parameterised"
            ],
        )

    mol, records = read_mol(file_path)

    # A protein PDB with multiple chains/fragments will parse in RDKit but
    # Meeko rejects it later with a confusing "fragments" error.  Detect early
    # and direct the user to the receptor panel instead.
    num_frags = len(Chem.GetMolFrags(mol))
    if num_frags > 1:
        raise PreparationError(
            f"{file_path.name} contains {num_frags} disconnected fragments "
            f"(e.g. a multi-chain protein). Single molecules belong in the ligand "
            f"panel; for protein receptors, use the receptor preparation panel."
        )

    # Zero atoms after parsing means the file was unreadable or empty.
    if mol.GetNumAtoms() == 0:
        raise PreparationError(
            f"{file_path.name} contains no atoms; the file may be corrupted "
            "or in an unexpected format"
        )

    # Metal ions (Na+, K+, Mg2+, Ca2+, Zn2+, etc.) cannot be docked as ligands.
    # They have no bonds and Meeko cannot assign AutoDock atom types to them.
    # Extended set covers alkali, alkaline-earth, transition, and heavy metals.
    _METAL_ATOMIC_NUMS = {
        3, 5, 11, 12, 13, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
        37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50,
        55, 56, 57, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
    }
    heavy_atoms = [a for a in mol.GetAtoms() if a.GetAtomicNum() != 1]
    metal_atoms = [a for a in heavy_atoms if a.GetAtomicNum() in _METAL_ATOMIC_NUMS]
    is_metal_ion = heavy_atoms and len(metal_atoms) == len(heavy_atoms)

    # Organometallics (e.g. heme/Fe, cisplatin/Pt) contain both metal and organic
    # atoms. Meeko may fail on the metal center; warn early.
    is_organometallic = metal_atoms and 0 < len(metal_atoms) < len(heavy_atoms)

    has_3d = _has_3d(mol)
    explicit_h = _count_attached_hydrogens(mol)
    implicit_h = _count_implicit_hydrogens(mol)

    notes: list[str] = []
    if is_metal_ion:
        symbols = ", ".join(a.GetSymbol() for a in heavy_atoms)
        notes.append(
            f"metal ion ({symbols}) cannot be parameterised for docking; "
            "if this is a cofactor, it should be part of the receptor structure"
        )
    if is_organometallic:
        metal_syms = ", ".join(a.GetSymbol() for a in metal_atoms)
        notes.append(
            f"organometallic compound detected (metal centres: {metal_syms}); "
            "parameterisation may fail — if it does, remove the metal and treat "
            "it as part of the receptor"
        )
    if not has_3d:
        notes.append("no 3D coordinates: a conformer will be generated before docking")
    if explicit_h == 0 and implicit_h > 0:
        notes.append(
            f"hydrogens are implicit ({implicit_h} missing): they must be added, "
            "because docking scores depend on polar hydrogens"
        )
    if records > 1:
        notes.append(f"file holds {records} molecules; only the first is prepared")

    return LigandInspection(
        source=str(file_path),
        input_format=fmt,
        preparable=not is_metal_ion,
        atoms=mol.GetNumAtoms(),
        hydrogens=explicit_h,
        has_3d_coordinates=has_3d,
        rotatable_bonds=rdMolDescriptors.CalcNumRotatableBonds(mol),
        molecular_formula=rdMolDescriptors.CalcMolFormula(mol),
        molecular_weight=round(rdMolDescriptors.CalcExactMolWt(mol), 3),
        smiles=_canonical_smiles(mol),
        records=records,
        notes=notes,
    )


def _embed_3d(mol: Chem.Mol, options: LigandPrepOptions) -> bool:
    """Generate a 3D conformer in place. Returns whether geometry was relaxed."""
    params = AllChem.ETKDGv3()
    params.randomSeed = options.embed_seed
    params.useSmallRingTorsions = True

    try:
        result = AllChem.EmbedMolecule(mol, params)
    except Exception as exc:
        raise PreparationError(
            f"3D embedding failed: {brief_error(exc)}"
        ) from exc
    if result != 0:
        # A failed embedding must not be silently ignored: without coordinates
        # there is nothing to dock.
        raise PreparationError(
            "could not generate 3D coordinates with ETKDGv3; "
            "supply a molecule with a 3D conformer instead"
        )

    if not options.optimise_geometry:
        return False

    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            return AllChem.MMFFOptimizeMolecule(mol) == 0
        return AllChem.UFFOptimizeMolecule(mol) == 0
    except Exception as exc:  # noqa: BLE001 - force-field failures are not fatal
        log.warning("geometry optimisation failed, continuing: %s", exc)
        return False


def prepare_ligand(
    path: str | Path,
    options: LigandPrepOptions | None = None,
) -> LigandPreparation:
    """Parameterise a ligand file into PDBQT.

    Raises :class:`InvalidInputError` when the file cannot be read,
    :class:`UnsupportedFormatError` for the wrong extension, and
    :class:`PreparationError` when Meeko refuses the molecule.
    """
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    options = options or LigandPrepOptions()
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")

    if not is_supported(file_path, "ligand"):
        raise UnsupportedFormatError(
            f"unsupported ligand extension {file_path.suffix!r}; "
            "expected one of .mol .sdf .mol2 .pdb .pdbqt"
        )
    if file_path.suffix.lower() not in PREPARABLE_SUFFIXES:
        raise UnsupportedFormatError(
            f"{file_path.name} is already PDBQT; it does not need parameterisation"
        )

    mol, records = read_mol(file_path)
    warnings: list[str] = []
    if records > 1:
        warnings.append(f"file contains {records} molecules; only the first was prepared")

    input_atoms = mol.GetNumAtoms()
    if input_atoms == 0:
        raise PreparationError(
            f"{file_path.name} contains no atoms; the file may be corrupted "
            "or in an unexpected format"
        )
    had_3d = _has_3d(mol)

    # Meeko rejects implicit hydrogens outright, so this is not optional. When
    # 3D coordinates already exist the hydrogens must be placed from that
    # geometry: adding them without coordinates would leave them at the origin
    # and fabricate clashes that dominate the docking score.
    explicit_before = _count_attached_hydrogens(mol)
    if _count_implicit_hydrogens(mol) or explicit_before == 0:
        try:
            mol = Chem.AddHs(mol, addCoords=had_3d)
        except Exception as exc:
            raise PreparationError(
                f"failed to add hydrogens to {file_path.name}: {brief_error(exc)}"
            ) from exc
    hydrogens_added = _count_attached_hydrogens(mol) - explicit_before
    if hydrogens_added == 0 and _count_implicit_hydrogens(mol):
        raise PreparationError(
            f"{file_path.name} still has implicit hydrogens after AddHs; "
            "the molecule cannot be parameterised for docking"
        )

    conformer_generated = False
    geometry_optimised = False
    if not had_3d:
        geometry_optimised = _embed_3d(mol, options)
        conformer_generated = True

    mk_prep = MoleculePreparation(
        rigid_macrocycles=options.rigid_macrocycles,
        flexible_amides=options.flexible_amides,
        hydrate=options.hydrate,
        double_bond_penalty=options.double_bond_penalty,
    )
    with _captured_rdkit_messages() as messages:
        try:
            molsetups = mk_prep(mol)
        except Exception as exc:
            msg = str(exc)
            if "fragments" in msg and ("Must have 1" in msg or "fragment" in msg):
                raise PreparationError(
                    f"{file_path.name} contains multiple disconnected fragments "
                    f"(e.g. multi-chain proteins). Single molecules like ligands "
                    f"should be prepared here; for protein receptors, use the "
                    f"receptor preparation panel instead."
                ) from exc
            raise PreparationError(
                f"Meeko could not parameterise {file_path.name}: "
                f"{_explain(messages, str(exc))}"
            ) from exc

    if not molsetups:
        raise PreparationError(
            f"Meeko produced no molecule setup for {file_path.name}: "
            f"{_explain(messages, 'unsupported chemistry')}"
        )
    if len(molsetups) > 1:
        warnings.append(
            f"Meeko produced {len(molsetups)} setups (reactive docking); the first was used"
        )

    pdbqt, success, error_message = PDBQTWriterLegacy.write_string(molsetups[0])
    if not success:
        raise PreparationError(
            f"PDBQT writer rejected {file_path.name}: "
            f"{brief_error(error_message) if error_message else _explain(messages, 'unknown reason')}"
        )

    try:
        parsed = parse_pdbqt(pdbqt)
    except PdbqtError as exc:  # pragma: no cover - would mean a Meeko bug
        raise PreparationError(f"Meeko wrote unparsable PDBQT: {brief_error(exc)}") from exc

    pose = parsed.first_pose
    polar_hydrogens = sum(1 for atom in pose.atoms if atom.is_polar_hydrogen)
    mol_hydrogens = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 1)
    mol_heavy_atoms = mol.GetNumAtoms() - mol_hydrogens
    pose_heavy_atoms = pose.n_atoms - polar_hydrogens

    if parsed.smiles is None:
        warnings.append("no SMILES recorded in the PDBQT header; bond orders cannot be restored")
    # A TORSDOF that is missing or zero means the torsion tree was not recorded,
    # which is the case this warning exists for; comparing it against itself hid
    # exactly that.
    if pose.torsdof is None or pose.torsdof != parsed.rotatable_bonds:
        warnings.append(
            f"BRANCH records ({parsed.rotatable_bonds}) disagree with TORSDOF "
            f"({pose.torsdof}); the torsion tree may be incomplete"
        )
    if pose_heavy_atoms < mol_heavy_atoms:
        warnings.append(
            f"{mol_heavy_atoms - pose_heavy_atoms} heavy atom(s) were dropped during "
            f"conversion ({mol_heavy_atoms} -> {pose_heavy_atoms})"
        )

    return LigandPreparation(
        pdbqt=pdbqt,
        sdf=Chem.MolToMolBlock(mol),
        report=LigandReport(
            source=str(file_path),
            input_format=detect_format(file_path) or file_path.suffix.lstrip("."),
            input_atoms=input_atoms,
            hydrogens_added=hydrogens_added,
            conformer_generated=conformer_generated,
            geometry_optimised=geometry_optimised,
            output_atoms=pose.n_atoms,
            output_polar_hydrogens=polar_hydrogens,
            # PDBQT keeps heavy atoms and polar hydrogens only; the hydrogens it
            # leaves out are the non-polar ones. Counting dropped atoms instead
            # reported every lost heavy atom as a hydrogen.
            nonpolar_hydrogens_removed=mol_hydrogens - polar_hydrogens,
            rotatable_bonds=parsed.rotatable_bonds,
            total_charge=pose.total_charge,
            atom_types=dict(pose.atom_types),
            smiles=parsed.smiles,
            warnings=warnings,
        ),
    )
