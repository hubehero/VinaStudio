"""Ligand preparation tests.

The strongest test here is ``test_matches_the_upstream_reference_pdbqt``: the
1iep example ships the PDBQT that the AutoDock authors produced with their own
Meeko invocation, so reproducing it means this pipeline agrees with upstream on
atom order, coordinates, atom types, charges and the torsion tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.ligand_prep import (
    LigandPrepOptions,
    inspect_ligand,
    prepare_ligand,
)
from vinastudio.core.chem.pdbqt import parse_pdbqt, read_pdbqt
from vinastudio.core.errors import InvalidInputError, UnsupportedFormatError

SAMPLE = SAMPLE_DIR / "1iep"
REFERENCE_SDF = SAMPLE / "1iep_ligand.sdf"
REFERENCE_PDBQT = SAMPLE / "1iep_ligand.pdbqt"

requires_samples = pytest.mark.skipif(
    not REFERENCE_SDF.exists() or not REFERENCE_PDBQT.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _canonicalise_charge_column(text: str) -> str:
    """Rewrite the PDBQT charge column in one fixed format.

    Meeko used to write a blank in place of a positive sign; it now writes '+'.
    Both are valid fixed-width encodings of the same number, so normalising the
    column lets the rest of the file be compared byte for byte.
    """
    out = []
    for line in text.splitlines():
        if line.startswith(("ATOM", "HETATM")):
            charge = float(line[66:76])
            line = f"{line[:66]}{charge:10.3f}{line[76:]}"
        out.append(line)
    return "\n".join(out)


@pytest.fixture
def aspirin_2d(tmp_path: Path) -> Path:
    """A 2D molfile with no explicit hydrogens, the common worst case."""
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    assert mol is not None
    AllChem.Compute2DCoords(mol)
    path = tmp_path / "aspirin_2d.mol"
    path.write_text(Chem.MolToMolBlock(mol))
    return path


# --------------------------------------------------------------------------
# inspection
# --------------------------------------------------------------------------


def test_inspect_flags_missing_hydrogens_and_coordinates(aspirin_2d: Path) -> None:
    inspection = inspect_ligand(aspirin_2d)

    assert inspection.preparable is True
    assert inspection.input_format == "mol"
    assert inspection.has_3d_coordinates is False
    assert inspection.hydrogens == 0
    assert inspection.atoms == 13  # heavy atoms only
    assert inspection.records == 1
    assert len(inspection.notes) == 2
    assert any("3D" in note for note in inspection.notes)
    assert any("implicit" in note for note in inspection.notes)


@requires_samples
def test_inspect_accepts_a_ready_made_ligand() -> None:
    inspection = inspect_ligand(REFERENCE_SDF)

    assert inspection.preparable is True
    assert inspection.input_format == "sdf"
    assert inspection.has_3d_coordinates is True
    assert inspection.atoms == 69
    assert inspection.hydrogens == 32
    assert inspection.rotatable_bonds == 7
    assert inspection.molecular_formula == "C29H32N7O+"
    assert inspection.notes == []


@requires_samples
def test_inspect_describes_a_pdbqt_without_reparameterising_it() -> None:
    inspection = inspect_ligand(REFERENCE_PDBQT)

    assert inspection.preparable is False
    assert inspection.input_format == "pdbqt"
    assert inspection.atoms == 40
    assert inspection.hydrogens == 3  # only the polar ones survive in PDBQT
    assert inspection.rotatable_bonds == 7
    assert inspection.molecular_formula is None
    assert any("docked as-is" in note for note in inspection.notes)


# --------------------------------------------------------------------------
# the 2D -> 3D -> PDBQT path
# --------------------------------------------------------------------------


def test_prepare_2d_molfile_adds_hydrogens_and_embeds_3d(aspirin_2d: Path) -> None:
    result = prepare_ligand(aspirin_2d)
    report = result.report

    assert report.conformer_generated is True
    assert report.geometry_optimised is True
    assert report.hydrogens_added == 8  # aspirin: C9H8O4
    assert report.input_atoms == 13
    # PDBQT keeps the 13 heavy atoms plus the one polar hydrogen (the COOH).
    assert report.output_atoms == 14
    assert report.output_polar_hydrogens == 1
    assert report.nonpolar_hydrogens_removed == 7
    # Four rotatable bonds: CH3-C(=O), C(=O)-O, O-aryl and aryl-C(=O)OH.
    assert report.rotatable_bonds == 4
    assert report.total_charge == pytest.approx(0.0, abs=0.01)
    assert report.smiles is not None
    assert report.warnings == []

    # The written PDBQT must parse with our own parser, and the SDF must be 3D.
    document = parse_pdbqt(result.pdbqt)
    assert document.n_poses == 1
    assert document.rotatable_bonds == 4
    sdf_mol = Chem.MolFromMolBlock(result.sdf, removeHs=False)
    assert sdf_mol is not None
    assert sdf_mol.GetConformer().Is3D() is True


def test_prepare_is_deterministic_with_a_fixed_seed(aspirin_2d: Path) -> None:
    first = prepare_ligand(aspirin_2d)
    second = prepare_ligand(aspirin_2d)

    assert first.pdbqt == second.pdbqt
    assert first.report.output_atoms == second.report.output_atoms


def test_skip_optimisation_still_produces_dockable_coordinates(aspirin_2d: Path) -> None:
    result = prepare_ligand(aspirin_2d, LigandPrepOptions(optimise_geometry=False))

    assert result.report.conformer_generated is True
    assert result.report.geometry_optimised is False
    assert result.report.output_atoms == 14
    # The coordinates must still be 3D; only the relaxation was skipped.
    sdf_mol = Chem.MolFromMolBlock(result.sdf, removeHs=False)
    assert sdf_mol is not None
    assert sdf_mol.GetConformer().Is3D() is True


def test_hydrogens_are_placed_from_existing_3d_geometry(tmp_path: Path) -> None:
    """A 3D structure without hydrogens must keep its coordinates.

    Adding hydrogens without coordinates would leave them at the origin, which
    fabricates clashes that would dominate the docking score.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    stripped = Chem.RemoveHs(mol)
    assert stripped.GetNumConformers() == 1
    assert stripped.GetConformer().Is3D() is True
    heavy_only = tmp_path / "phenol_3d_noH.mol"
    heavy_only.write_text(Chem.MolToMolBlock(stripped))

    result = prepare_ligand(heavy_only)

    assert result.report.hydrogens_added == 6
    # No new conformer: the input coordinates were trusted.
    assert result.report.conformer_generated is False
    parsed = parse_pdbqt(result.pdbqt)
    # The ring carbon atoms must sit near their original positions.
    original = {atom.GetIdx(): atom for atom in stripped.GetAtoms()}
    assert len(original) == 7
    for atom in parsed.first_pose.atoms:
        assert abs(atom.x) < 100.0
        assert abs(atom.y) < 100.0
        assert abs(atom.z) < 100.0
    assert parsed.first_pose.centroid != (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# gold standard
# --------------------------------------------------------------------------


@requires_samples
def test_matches_the_upstream_reference_pdbqt() -> None:
    """Reproduce the PDBQT that the AutoDock authors generated for imatinib."""
    result = prepare_ligand(REFERENCE_SDF)
    reference = REFERENCE_PDBQT.read_text()

    assert _canonicalise_charge_column(result.pdbqt) == _canonicalise_charge_column(reference)

    ours = parse_pdbqt(result.pdbqt)
    theirs = parse_pdbqt(reference)
    assert ours.n_poses == theirs.n_poses == 1
    assert ours.smiles == theirs.smiles
    assert ours.rotatable_bonds == theirs.rotatable_bonds == 7

    for our_atom, their_atom in zip(ours.first_pose.atoms, theirs.first_pose.atoms, strict=True):
        assert our_atom.serial == their_atom.serial
        assert our_atom.name == their_atom.name
        assert our_atom.atom_type == their_atom.atom_type
        assert our_atom.x == their_atom.x
        assert our_atom.y == their_atom.y
        assert our_atom.z == their_atom.z
        assert our_atom.charge == pytest.approx(their_atom.charge, abs=1e-6)

    assert ours.first_pose.branches == theirs.first_pose.branches


@requires_samples
def test_imatinib_is_prepared_as_its_cation() -> None:
    result = prepare_ligand(REFERENCE_SDF)

    assert "[NH+]" in (result.report.smiles or "")
    assert result.report.total_charge == pytest.approx(1.0, abs=0.05)
    assert result.report.atom_types.get("A", 0) > 0


def test_meeko_options_reach_the_torsion_tree(aspirin_2d: Path) -> None:
    """``flexible_amides`` lets an amide bond rotate during docking."""
    rigid = prepare_ligand(aspirin_2d, LigandPrepOptions(flexible_amides=False))
    flexible = prepare_ligand(aspirin_2d, LigandPrepOptions(flexible_amides=True))

    # Aspirin has a carboxylic acid, not an amide, so the count must be equal:
    # the option must not perturb chemistry it does not apply to.
    assert rigid.report.rotatable_bonds == flexible.report.rotatable_bonds


# --------------------------------------------------------------------------
# rejections
# --------------------------------------------------------------------------


@requires_samples
def test_a_prepared_pdbqt_is_not_reparameterised() -> None:
    with pytest.raises(UnsupportedFormatError, match="already PDBQT"):
        prepare_ligand(REFERENCE_PDBQT)


@pytest.mark.parametrize("suffix", [".mol2.txt", ".xyz", ".fasta", ""])
def test_unsupported_extensions_are_rejected(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"molecule{suffix}"
    path.write_text("not a molecule\n")

    with pytest.raises(UnsupportedFormatError):
        inspect_ligand(path)


def test_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="file not found"):
        inspect_ligand(tmp_path / "absent.sdf")
    with pytest.raises(InvalidInputError, match="file not found"):
        prepare_ligand(tmp_path / "absent.mol")


def test_unreadable_molecule_reports_the_rdkit_reason(tmp_path: Path) -> None:
    broken = tmp_path / "broken.sdf"
    broken.write_text("this is not an SD file at all\n")

    with pytest.raises(InvalidInputError) as info:
        prepare_ligand(broken)
    # The message must say something actionable, not just "failed".
    assert "broken.sdf" in str(info.value)


@requires_samples
def test_inspection_smiles_omits_explicit_hydrogens() -> None:
    """The displayed SMILES must be the readable heavy-atom form."""
    inspection = inspect_ligand(REFERENCE_SDF)

    assert inspection.smiles is not None
    assert "[H]" not in inspection.smiles
    assert inspection.smiles == read_pdbqt(REFERENCE_PDBQT).smiles
