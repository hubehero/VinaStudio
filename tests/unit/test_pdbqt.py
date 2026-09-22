"""PDBQT parsing tests against the 1iep reference example.

Where it matters, the expectations are re-derived from the raw file inside the
test (see ``_independent_atom_scan``) instead of being copied out of the parser,
so a column-slicing mistake cannot pass by agreeing with itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.pdbqt import PdbqtError, parse_pdbqt, read_pdbqt

SAMPLE = SAMPLE_DIR / "1iep"
LIGAND_INPUT = SAMPLE / "1iep_ligand.pdbqt"
DOCKING_OUTPUT = SAMPLE / "1iep_ligand_vina_out.pdbqt"

#: Values published in the AutoDock Vina basic-docking tutorial for this system.
PUBLISHED_ENERGIES = (-13.234, -11.293, -11.281, -11.146)
IMATINIB_SMILES = "Cc1ccc(NC(=O)c2ccc(CN3CC[NH+](C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1"

pytestmark = pytest.mark.skipif(
    not LIGAND_INPUT.exists() or not DOCKING_OUTPUT.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _independent_atom_scan(path: Path) -> list[dict[str, object]]:
    """Extract the atom fields with a whitespace-delimited regex.

    PDQBT's fixed columns are what the parser slices, so this oracle deliberately
    tokenises on whitespace instead: agreement between the two means the column
    offsets are right, not that one mistake is repeated twice. Meeko leaves the
    chain column blank, so it is not part of the pattern.
    """
    pattern = re.compile(
        r"^ATOM\s+(?P<serial>\d+)\s+(?P<name>\S+)\s+(?P<resn>\S+)\s+"
        r"(?P<resid>\d+)\s+(?P<x>-?\d+\.\d+)\s+(?P<y>-?\d+\.\d+)\s+(?P<z>-?\d+\.\d+)\s+"
        r"(?P<occ>-?\d+\.\d+)\s+(?P<bfac>-?\d+\.\d+)\s+(?P<charge>-?\d+\.\d+)\s+"
        r"(?P<type>\S+)"
    )
    found = []
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            found.append(match.groupdict())
    return found


def test_single_pose_input_is_parsed() -> None:
    document = read_pdbqt(LIGAND_INPUT)

    assert document.n_poses == 1
    assert document.is_multi_model is False
    assert document.source == str(LIGAND_INPUT)

    pose = document.first_pose
    assert pose.index == 1
    assert pose.n_atoms == 40
    # A docking input has no affinity yet.
    assert pose.energy is None
    assert pose.rmsd_lower_bound is None


def test_torsion_tree_matches_the_torsion_degrees_of_freedom() -> None:
    """``BRANCH`` records and ``TORSDOF`` must agree; they are both the search DOF."""
    document = read_pdbqt(LIGAND_INPUT)
    pose = document.first_pose

    assert pose.rotatable_bonds == 7
    assert pose.torsdof == 7
    assert document.rotatable_bonds == 7
    assert all(branch.parent_serial > 0 for branch in pose.branches)
    assert all(branch.child_serial > 0 for branch in pose.branches)


def test_smiles_remark_is_captured() -> None:
    """The SMILES header is the only source of bond orders for the pose."""
    document = read_pdbqt(LIGAND_INPUT)
    assert document.smiles == IMATINIB_SMILES


def test_smiles_and_hydrogen_index_maps_are_even_length() -> None:
    document = read_pdbqt(LIGAND_INPUT)
    assert len(document.smiles_index_map) % 2 == 0
    assert len(document.hydrogen_parents) % 2 == 0
    # 40 atoms of which 3 are polar hydrogens -> 37 mapped to SMILES indices.
    assert len(document.smiles_index_map) // 2 == 37
    assert len(document.hydrogen_parents) // 2 == 3


def test_atom_columns_match_an_independent_scan() -> None:
    oracle = _independent_atom_scan(LIGAND_INPUT)
    pose = read_pdbqt(LIGAND_INPUT).first_pose

    assert len(oracle) == len(pose.atoms) == 40
    for expected, atom in zip(oracle, pose.atoms, strict=True):
        assert atom.serial == int(expected["serial"])
        assert atom.name == expected["name"]
        assert atom.resname == expected["resn"]
        assert atom.atom_type == expected["type"]
        assert atom.x == pytest.approx(float(expected["x"]))
        assert atom.y == pytest.approx(float(expected["y"]))
        assert atom.z == pytest.approx(float(expected["z"]))
        assert atom.charge == pytest.approx(float(expected["charge"]))


def test_every_atom_type_is_a_known_autodock_type() -> None:
    known = {
        "A", "C", "N", "NA", "OA", "SA", "S", "H", "HD", "HS",
        "F", "Cl", "Br", "I", "P", "Si", "B", "Mg", "Mn", "Zn", "Ca", "Fe",
    }
    pose = read_pdbqt(LIGAND_INPUT).first_pose
    assert set(pose.atom_types) <= known
    # Aromatic carbons and carbonyl oxygens must both be present in imatinib.
    assert pose.atom_types["A"] > 0
    assert pose.atom_types["OA"] > 0
    assert sum(pose.atom_types.values()) == pose.n_atoms


def test_multi_model_output_is_parsed_with_energies() -> None:
    document = read_pdbqt(DOCKING_OUTPUT)

    assert document.n_poses == 4
    assert document.is_multi_model is True
    assert tuple(document.energies) == PUBLISHED_ENERGIES
    assert [pose.index for pose in document.poses] == [1, 2, 3, 4]
    assert all(pose.n_atoms == 40 for pose in document.poses)
    assert all(pose.torsdof == 7 for pose in document.poses)


def test_first_pose_rmsd_is_zero_and_the_best_pose_is_the_lowest_energy() -> None:
    document = read_pdbqt(DOCKING_OUTPUT)
    best = document.best_pose()

    assert best is not None
    assert best.index == 1
    assert best.energy == PUBLISHED_ENERGIES[0]
    # RMSD is measured against the best mode, so pose 1 is zero by definition.
    assert best.rmsd_lower_bound == 0.0
    assert best.rmsd_upper_bound == 0.0

    assert document.poses[1].rmsd_lower_bound == pytest.approx(0.986)
    assert document.poses[1].rmsd_upper_bound == pytest.approx(1.681)


def test_poses_land_inside_the_documented_docking_box() -> None:
    """The tutorial box centre; a parser reading columns wrongly would not."""
    centre = (15.190, 53.903, 16.917)
    half = 10.0
    document = read_pdbqt(DOCKING_OUTPUT)

    for pose in document.poses:
        for axis, expected in enumerate(centre):
            assert abs(pose.centroid[axis] - expected) < half


def test_summary_shape_matches_the_api_contract() -> None:
    summary = read_pdbqt(DOCKING_OUTPUT).summary()

    assert summary["poses"] == 4
    assert summary["atoms"] == 40
    assert summary["rotatableBonds"] == 7
    assert summary["torsdof"] == 7
    assert summary["smiles"] == IMATINIB_SMILES
    assert summary["energies"] == list(PUBLISHED_ENERGIES)
    assert isinstance(summary["atomTypes"], dict)


def test_total_charge_confirms_the_protonated_species() -> None:
    """Imatinib is prepared as its cation; Meeko writes [NH+] in the SMILES."""
    pose = read_pdbqt(LIGAND_INPUT).first_pose

    assert "[NH+]" in (read_pdbqt(LIGAND_INPUT).smiles or "")
    assert pose.total_charge == pytest.approx(1.0, abs=0.05)


def test_parse_from_string_matches_parse_from_file() -> None:
    from_file = read_pdbqt(LIGAND_INPUT)
    from_string = parse_pdbqt(LIGAND_INPUT.read_text())

    assert from_string.n_poses == from_file.n_poses
    assert from_string.first_pose.coordinates() == from_file.first_pose.coordinates()
    assert from_string.smiles == from_file.smiles
    assert from_string.source is None


def test_polar_hydrogen_and_element_helpers() -> None:
    pose = read_pdbqt(LIGAND_INPUT).first_pose
    hydrogens = [atom for atom in pose.atoms if atom.is_polar_hydrogen]

    # Three polar hydrogens: the piperazine NH+ and the two amide/amine N-H.
    assert len(hydrogens) == 3
    assert {atom.element for atom in hydrogens} == {"H"}
    assert {atom.atom_type for atom in hydrogens} == {"HD"}

    heavy = [atom for atom in pose.atoms if not atom.is_polar_hydrogen]
    assert len(heavy) == 37
    assert {atom.element for atom in heavy} <= {"C", "N", "O"}


@pytest.mark.parametrize(
    "content",
    [
        "",
        "REMARK SMILES CCO\n",
        "this is not a chemical file\n",
    ],
)
def test_content_without_atoms_is_rejected(content: str) -> None:
    with pytest.raises(PdbqtError):
        parse_pdbqt(content)


def test_missing_file_raises_a_domain_error(tmp_path: Path) -> None:
    with pytest.raises(PdbqtError):
        read_pdbqt(tmp_path / "absent.pdbqt")
