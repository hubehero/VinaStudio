"""Export tests: PDBQT -> SDF and PDBQT -> PDB.

The SDF path is the load-bearing one, because it is the only way a docked pose
reaches the 3D view. If it silently dropped the SMILES-derived chemistry, poses
would render with wrong bond orders and nobody would notice.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.export import pdbqt_to_pdb, poses_to_sdf
from vinastudio.core.chem.ligand_prep import prepare_ligand
from vinastudio.core.chem.pdbqt import parse_pdbqt, read_pdbqt
from vinastudio.core.errors import InvalidInputError, PreparationError

SAMPLE = SAMPLE_DIR / "1iep"
DOCKING_OUTPUT = SAMPLE / "1iep_ligand_vina_out.pdbqt"
LIGAND_INPUT = SAMPLE / "1iep_ligand.pdbqt"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
REFERENCE_SDF = SAMPLE / "1iep_ligand.sdf"

requires_samples = pytest.mark.skipif(
    not DOCKING_OUTPUT.exists() or not LIGAND_INPUT.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


# --------------------------------------------------------------------------
# PDBQT -> SDF
# --------------------------------------------------------------------------


@requires_samples
def test_every_pose_becomes_an_sd_record() -> None:
    result = poses_to_sdf(DOCKING_OUTPUT)

    assert result.n_poses == 4
    assert result.sdf.count("$$$$") == 4
    assert result.titles == ["pose_1", "pose_2", "pose_3", "pose_4"]
    assert result.energies == pytest.approx([-13.234, -11.293, -11.281, -11.146])
    assert result.warnings == []
    # 40 PDBQT atoms become 69 atoms once the non-polar hydrogens are restored.
    assert result.atoms == 69


@requires_samples
def test_affinities_are_written_as_sd_properties() -> None:
    result = poses_to_sdf(DOCKING_OUTPUT)

    assert ">  <affinity_kcal_per_mol>" in result.sdf
    assert "-13.234" in result.sdf
    assert ">  <rmsd_lb>" in result.sdf
    assert ">  <pose>" in result.sdf


def _heavy_smiles(mol: Chem.Mol) -> str:
    """Canonical SMILES ignoring explicit hydrogens, so comparisons are chemical."""
    return Chem.MolToSmiles(Chem.RemoveHs(mol))


@requires_samples
def test_sdf_reads_back_with_correct_bond_orders() -> None:
    """Bond orders come from the header SMILES, not from distance guessing."""
    result = poses_to_sdf(DOCKING_OUTPUT)

    supplier = Chem.SDMolSupplier()
    supplier.SetData(result.sdf, removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    assert len(molecules) == 4

    expected = read_pdbqt(DOCKING_OUTPUT).smiles
    assert expected is not None
    expected_smiles = _heavy_smiles(Chem.MolFromSmiles(expected))
    for mol in molecules:
        assert mol.GetNumAtoms() == 69
        # The protonated cation must survive the round trip.
        assert _heavy_smiles(mol) == expected_smiles

    # Aromatic rings must be perceived as aromatic, which only works if the bond
    # orders were restored rather than inferred from coordinates.
    aromatic = sum(1 for atom in molecules[0].GetAtoms() if atom.GetIsAromatic())
    assert aromatic >= 16  # two benzene rings plus a pyridine and a pyrimidine


@requires_samples
def test_poses_keep_their_own_coordinates() -> None:
    """Each SD record must hold that pose's geometry, not the first pose's.

    The SDF carries all 69 atoms while the PDBQT carries 40, so the check is
    that every PDBQT coordinate is present in the matching SD record.
    """
    result = poses_to_sdf(DOCKING_OUTPUT)
    document = read_pdbqt(DOCKING_OUTPUT)

    supplier = Chem.SDMolSupplier()
    supplier.SetData(result.sdf, removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    assert len(molecules) == document.n_poses

    for index, (mol, pose) in enumerate(zip(molecules, document.poses, strict=True)):
        conformer = mol.GetConformer()
        sdf_points = {
            (
                round(conformer.GetAtomPosition(i).x, 3),
                round(conformer.GetAtomPosition(i).y, 3),
                round(conformer.GetAtomPosition(i).z, 3),
            )
            for i in range(mol.GetNumAtoms())
        }
        pose_points = {(atom.x, atom.y, atom.z) for atom in pose.atoms}
        assert pose_points <= sdf_points, f"pose {index + 1} coordinates were not copied"

    # The poses really are different from each other.
    assert molecules[0].GetConformer().GetAtomPosition(0).x != pytest.approx(
        molecules[3].GetConformer().GetAtomPosition(0).x
    )


@requires_samples
def test_a_single_pose_input_converts_too() -> None:
    result = poses_to_sdf(LIGAND_INPUT)

    assert result.n_poses == 1
    assert result.sdf.count("$$$$") == 1
    # A docking input carries no affinity, so none is invented.
    assert result.energies == []
    assert any("no VINA RESULT" in warning for warning in result.warnings)
    assert "affinity_kcal_per_mol" not in result.sdf


@requires_samples
def test_sdf_from_text_matches_sdf_from_file() -> None:
    """The API hands Meeko strings around, so text input must work."""
    from_file = poses_to_sdf(DOCKING_OUTPUT)
    from_text = poses_to_sdf(DOCKING_OUTPUT.read_text())

    assert from_text.sdf == from_file.sdf
    assert from_text.n_poses == from_file.n_poses


@requires_samples
def test_conversion_of_a_freshly_prepared_ligand_works(tmp_path: Path) -> None:
    """End to end: SDF -> PDBQT -> SDF must preserve the molecule."""
    prepared = prepare_ligand(REFERENCE_SDF)
    output = tmp_path / "fresh.pdbqt"
    output.write_text(prepared.pdbqt)

    result = poses_to_sdf(output)
    first_record = result.sdf.split("$$$$")[0]
    mol = Chem.MolFromMolBlock(first_record, removeHs=False)
    assert mol is not None

    smiles = read_pdbqt(output).smiles
    assert smiles is not None
    assert _heavy_smiles(mol) == _heavy_smiles(Chem.MolFromSmiles(smiles))


# --------------------------------------------------------------------------
# PDBQT -> PDB
# --------------------------------------------------------------------------


@requires_samples
def test_receptor_pdbqt_becomes_renderable_pdb() -> None:
    from vinastudio.core.chem.receptor_prep import prepare_receptor

    prepared = prepare_receptor(RECEPTOR_PDB)
    pdb = pdbqt_to_pdb(prepared.pdbqt, title="prepared receptor")

    lines = pdb.splitlines()
    assert lines[0].startswith("TITLE")
    assert lines[-1] == "END"
    atom_lines = [line for line in lines if line.startswith("ATOM")]
    assert len(atom_lines) == parse_pdbqt(prepared.pdbqt).first_pose.n_atoms

    # AutoDock charge and type columns must be gone: those live in columns 67-79.
    for line in atom_lines[:50]:
        assert len(line) <= 80
        assert line[76:78].strip() in {"C", "N", "O", "S", "H"}

    # Residue information must survive so the cartoon renders.
    assert "MET" in pdb
    assert " A 225" in pdb


@requires_samples
def test_ligand_pose_becomes_pdb_with_correct_elements() -> None:
    pdb = pdbqt_to_pdb(DOCKING_OUTPUT, model=0)
    lines = [line for line in pdb.splitlines() if line.startswith("ATOM")]

    assert len(lines) == 40
    elements = {line[76:78].strip() for line in lines}
    assert elements == {"C", "N", "O", "H"}
    assert any("VINA RESULT" in line for line in pdb.splitlines())

    # Elements must agree with the AutoDock types they came from.
    pose = read_pdbqt(DOCKING_OUTPUT).poses[0]
    for line, atom in zip(lines, pose.atoms, strict=True):
        element = line[76:78].strip()
        if atom.atom_type in {"A", "C"}:
            assert element == "C"
        elif atom.atom_type == "OA":
            assert element == "O"
        elif atom.atom_type == "HD":
            assert element == "H"


@requires_samples
def test_pdb_export_selects_the_requested_pose() -> None:
    first = pdbqt_to_pdb(DOCKING_OUTPUT, model=0)
    third = pdbqt_to_pdb(DOCKING_OUTPUT, model=2)

    assert first != third
    assert "-11.281" in third


@requires_samples
def test_requesting_a_pose_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(InvalidInputError, match="does not exist"):
        pdbqt_to_pdb(DOCKING_OUTPUT, model=9)


def test_a_parsed_document_without_its_source_cannot_be_exported() -> None:
    from vinastudio.core.chem.pdbqt import parse_pdbqt as parse

    document = parse(
        "ATOM      1  C   UNL     1       0.000   0.000   0.000  1.00  0.00     0.000 C\n"
    )
    with pytest.raises(InvalidInputError, match="source file"):
        poses_to_sdf(document)


@requires_samples
def test_conversion_failure_names_the_missing_smiles() -> None:
    """Without the header SMILES there is no way to restore bond orders."""
    stripped = "\n".join(
        line
        for line in DOCKING_OUTPUT.read_text().splitlines()
        if not line.startswith("REMARK SMILES")
    )
    with pytest.raises(PreparationError):
        poses_to_sdf(stripped)
