"""Receptor preparation tests, using the 1iep reference structure.

The reference file is deliberately hostile: its second line holds a single
``HB2`` atom of ``SER A 438`` while the rest of that residue sits near the end,
which makes Meeko refuse the structure until the atoms are regrouped. That is
exactly the case ``normalise_pdb_atom_order`` exists for, so it is tested both
ways — with and without the normalisation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.pdb_lines import scan_residues, split_solvent
from vinastudio.core.chem.pdbqt import parse_pdbqt
from vinastudio.core.chem.receptor_prep import (
    ReceptorPrepOptions,
    inspect_receptor,
    normalise_pdb_atom_order,
    prepare_receptor,
)
from vinastudio.core.errors import (
    InvalidInputError,
    PreparationError,
    UnsupportedFormatError,
    VinaStudioError,
)

REFERENCE_PDB = SAMPLE_DIR / "1iep" / "1iep_receptorH.pdb"
REFERENCE_RECEPTOR_PDBQT = SAMPLE_DIR / "1iep" / "1iep_receptor.pdbqt"

requires_samples = pytest.mark.skipif(
    not REFERENCE_PDB.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)

#: Residues present in the c-Abl kinase-domain construct.
FIRST_RESIDUE = "A:225"
LAST_RESIDUE = "A:498"
STRAY_RESIDUE = "A:438"

#: Minimal valid mmCIF content with one ALA residue (4 atoms) for testing format
#: detection and conversion.  Matches the real RCSB atom_site columns.
MMCIF_SAMPLE = """\
data_TEST
_entry.id   TEST

loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.pdbx_formal_charge
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
ATOM   1   N N   . ALA A 1 1  ?  0.000  0.000  0.000  1.00  10.0 ? 1 ALA A N   1
ATOM   2   C CA  . ALA A 1 1  ?  1.500  0.000  0.000  1.00  10.0 ? 1 ALA A CA  1
ATOM   3   C C   . ALA A 1 1  ?  2.500  1.200  0.000  1.00  10.0 ? 1 ALA A C   1
ATOM   4   O O   . ALA A 1 1  ?  2.500  2.400  0.000  1.00  10.0 ? 1 ALA A O   1
"""


def _element_totals(pose) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Count atoms by element, merging AutoDock's aromatic/non-aromatic pairs."""
    merged = {"C": ("C", "A"), "S": ("S", "SA"), "N": ("N", "NA"), "O": ("OA",)}
    totals: dict[str, int] = {}
    for atom in pose.atoms:
        for element, types in merged.items():
            if atom.atom_type in types:
                totals[element] = totals.get(element, 0) + 1
                break
        else:
            totals[atom.atom_type] = totals.get(atom.atom_type, 0) + 1
    return totals


@pytest.fixture(scope="module")
def receptor_text() -> str:
    return REFERENCE_PDB.read_text()


# --------------------------------------------------------------------------
# atom order normalisation
# --------------------------------------------------------------------------


@requires_samples
def test_the_reference_file_really_has_a_split_residue(receptor_text: str) -> None:
    """Guard the premise of the normalisation test below."""
    lines = receptor_text.splitlines()
    assert lines[0].startswith(("HEADER", "REMARK", "CRYST", "COMPND", "TITLE"))
    assert lines[1].startswith("ATOM")
    assert lines[1][17:20].strip() == "SER"
    assert lines[1][22:27].strip() == "438"
    # The rest of SER 438 appears thousands of lines later.
    later = [
        i
        for i, line in enumerate(lines)
        if line.startswith("ATOM") and line[17:20].strip() == "SER" and line[22:27].strip() == "438"
    ]
    assert max(later) > 3400


@requires_samples
def test_normalisation_regroups_the_split_residue(receptor_text: str) -> None:
    normalised, changed = normalise_pdb_atom_order(receptor_text)

    assert changed is True
    lines = normalised.splitlines()
    # The stray atom is no longer the first atom of the file.
    assert not (lines[1][17:20].strip() == "SER" and lines[1][22:27].strip() == "438")

    # Every residue's atoms are contiguous now, and none were lost.
    keys = [
        f"{line[21:22].strip()}:{line[22:27].strip()}"
        for line in lines
        if line.startswith(("ATOM", "HETATM"))
    ]
    runs = [key for i, key in enumerate(keys) if i == 0 or keys[i - 1] != key]
    assert len(runs) == len(set(runs)), "a residue is still split across the file"
    assert len(keys) == sum(
        1 for line in receptor_text.splitlines() if line.startswith(("ATOM", "HETATM"))
    )


@requires_samples
def test_normalisation_preserves_residue_order(receptor_text: str) -> None:
    normalised, _ = normalise_pdb_atom_order(receptor_text)
    keys = [
        f"{line[21:22].strip()}:{line[22:27].strip()}"
        for line in normalised.splitlines()
        if line.startswith("ATOM")
    ]

    ordered = list(dict.fromkeys(keys))
    assert ordered[0] == FIRST_RESIDUE
    assert ordered[-1] == LAST_RESIDUE
    assert STRAY_RESIDUE in ordered
    # The construct runs from 225 to 498, so the sequence must be monotonic.
    numbers = [int(key.split(":")[1]) for key in ordered]
    assert numbers == sorted(numbers)


def test_normalisation_leaves_a_clean_file_untouched() -> None:
    clean = (
        "ATOM      1  N   MET A   1      0.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      2  CA  MET A   1      1.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      3  N   ALA A   2      2.000   0.000   0.000  1.00  0.00           N\n"
    )
    normalised, changed = normalise_pdb_atom_order(clean)

    assert changed is False
    assert normalised == clean


# --------------------------------------------------------------------------
# inspection
# --------------------------------------------------------------------------


@requires_samples
def test_inspect_reports_the_construct(receptor_text: str) -> None:
    inspection = inspect_receptor(REFERENCE_PDB)

    assert inspection.preparable is True
    assert inspection.input_format == "pdb"
    assert inspection.chains == 1
    # 274 template-matched residues spanning A:225..A:498.
    assert inspection.residues == 274
    assert inspection.atoms > 4000
    assert inspection.waters == []
    assert inspection.hetero == []
    assert "SER" in inspection.residue_names


@requires_samples
def test_scan_and_classify_separate_waters_from_other_hetero() -> None:
    text = (
        "ATOM      1  N   MET A   1      0.000   0.000   0.000  1.00  0.00           N\n"
        "HETATM    2  O   HOH A 500      1.000   0.000   0.000  1.00  0.00           O\n"
        "HETATM    3 ZN    ZN A 501      2.000   0.000   0.000  1.00  0.00          ZN\n"
        "HETATM    4  C1  LIG A 502      3.000   0.000   0.000  1.00  0.00           C\n"
    )
    residues = scan_residues(text)
    waters, hetero = split_solvent(residues)

    assert waters == ["A:500"]
    assert sorted(hetero) == ["A:501", "A:502"]
    assert "A:1" not in waters + hetero  # polymer atoms are never stripped


# --------------------------------------------------------------------------
# preparation
# --------------------------------------------------------------------------


@requires_samples
def test_prepare_the_reference_receptor() -> None:
    result = prepare_receptor(REFERENCE_PDB)
    report = result.report

    assert report.normalised_atom_order is True
    assert report.valid_residues == 274
    assert report.ignored_residues == []
    assert report.deleted_waters == []
    assert report.deleted_hetero == []
    assert report.flexible_residues == []
    assert report.include_hydrogens is True
    assert report.warnings == []

    # AutoDock atom types, including the polar hydrogens docking needs.
    assert set(report.atom_types) <= {"C", "A", "N", "NA", "OA", "SA", "S", "HD", "H"}
    assert report.atom_types["HD"] > 400
    assert report.atom_types["OA"] > 400
    assert report.output_atoms == sum(report.atom_types.values())

    # The rigid file must parse, and the PDB is for rendering.
    parsed = parse_pdbqt(result.pdbqt)
    assert parsed.n_poses == 1
    assert result.flex_pdbqt is None
    assert result.pdb.startswith("ATOM")
    assert len(result.pdb.splitlines()) > 4000


@requires_samples
def test_prepared_receptor_matches_the_upstream_file_closely() -> None:
    """Compare this pipeline's receptor against the one upstream Meeko produced.

    Geometry and composition must agree exactly; the *charges* must not, and
    that is the interesting part. Meeko changed its methionine sulfur handling
    between the version that wrote the upstream file and the one pinned here:
    ``SG`` is now typed ``S`` (non-polar thioether) with a charge of about
    -0.79, where it used to be ``SA`` with about -0.10. Across the whole
    receptor that is a mean absolute difference of ~0.02 e per atom and 430
    atoms shifted by more than 0.05 e.

    The bounds below are deliberately tight around the measured difference so
    that a further change in parameterisation fails this test instead of
    quietly altering every docking score.
    """
    if not REFERENCE_RECEPTOR_PDBQT.exists():
        pytest.skip("upstream receptor PDBQT not fetched")

    ours = parse_pdbqt(prepare_receptor(REFERENCE_PDB).pdbqt).first_pose
    theirs = parse_pdbqt(REFERENCE_RECEPTOR_PDBQT.read_text()).first_pose

    # --- must be identical -------------------------------------------------
    assert ours.n_atoms == theirs.n_atoms
    assert _element_totals(ours) == _element_totals(theirs)
    assert sorted(atom.coordinates for atom in ours.atoms) == sorted(
        atom.coordinates for atom in theirs.atoms
    )
    # Every atom type except sulfur matches exactly.
    for atom_type in ("C", "A", "N", "NA", "OA", "HD", "H"):
        assert ours.atom_types.get(atom_type, 0) == theirs.atom_types.get(atom_type, 0), atom_type
    # Sulfur is conserved, only the five methionine thioethers are relabelled.
    ours_sulfur = ours.atom_types.get("S", 0) + ours.atom_types.get("SA", 0)
    theirs_sulfur = theirs.atom_types.get("S", 0) + theirs.atom_types.get("SA", 0)
    assert ours_sulfur == theirs_sulfur == 18
    assert ours.atom_types.get("S", 0) == 5
    assert theirs.atom_types.get("S", 0) == 0
    assert ours.atom_types.get("SA", 0) == theirs.atom_types.get("SA", 0) - 5

    # Pin exactly which atoms moved: thiol/thioether sulfurs, S -> SA.
    theirs_by_coordinate = {
        (round(a.x, 3), round(a.y, 3), round(a.z, 3)): a for a in theirs.atoms
    }
    relabelled = [
        (atom.name, atom.resname, atom.atom_type, theirs_by_coordinate[key].atom_type)
        for atom in ours.atoms
        if (key := (round(atom.x, 3), round(atom.y, 3), round(atom.z, 3))) in theirs_by_coordinate
        and atom.atom_type != theirs_by_coordinate[key].atom_type
    ]
    assert len(relabelled) == 5
    assert {name for name, *_ in relabelled} == {"SG"}
    assert {(ours_type, theirs_type) for _, _, ours_type, theirs_type in relabelled} == {
        ("S", "SA")
    }
    # Methionine thioethers and cysteine thiols are both affected.
    assert {resname for _, resname, *_ in relabelled} <= {"MET", "CYS"}

    # --- the documented difference ----------------------------------------
    _assert_charge_drift_is_within_the_known_meeko_change(ours, theirs)


def _assert_charge_drift_is_within_the_known_meeko_change(ours, theirs) -> None:  # type: ignore[no-untyped-def]
    by_coordinate = {(round(a.x, 3), round(a.y, 3), round(a.z, 3)): a for a in theirs.atoms}
    differences = [
        abs(atom.charge - by_coordinate[key].charge)
        for atom in ours.atoms
        if (key := (round(atom.x, 3), round(atom.y, 3), round(atom.z, 3))) in by_coordinate
    ]

    assert len(differences) == ours.n_atoms
    mean = sum(differences) / len(differences)
    assert mean < 0.03, f"mean per-atom charge drift grew to {mean:.4f} e"
    assert max(differences) < 0.75, f"largest per-atom charge drift grew to {max(differences):.3f} e"
    total_absolute_drift = sum(differences)
    assert total_absolute_drift == pytest.approx(58.5, abs=2.0), (
        f"total absolute charge drift is {total_absolute_drift:.2f} e"
    )

    total_drift = abs(ours.total_charge - theirs.total_charge)
    assert total_drift < 1.5, f"net charge drifted by {total_drift:.3f} e"


@requires_samples
def test_preparation_is_deterministic() -> None:
    first = prepare_receptor(REFERENCE_PDB)
    second = prepare_receptor(REFERENCE_PDB)

    assert first.pdbqt == second.pdbqt
    assert first.pdb == second.pdb


def test_without_normalisation_meeko_refuses_the_split_residue() -> None:
    """Reproduce the upstream failure, so the workaround stays justified."""
    header = "ATOM   3429  HB2 SER A 438      13.612  67.338  33.314  1.00  0.00           H\n"
    body = "".join(
        f"ATOM   {i:4d}  CA  ALA A {i:3d}      {i:6.3f}   0.000   0.000  1.00  0.00           C\n"
        for i in range(2)
    )
    # The stray atom belongs to a residue that also appears after the others.
    split = (
        header
        + "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n"
        + body
        + "HETATM 9999  OG  SER A 438       1.000   1.000   1.000  1.00  0.00           O\n"
    )
    from vinastudio.core.chem.receptor_prep import normalise_pdb_atom_order

    normalised, changed = normalise_pdb_atom_order(split)
    assert changed is True
    keys = [
        f"{line[21:22].strip()}:{line[22:27].strip()}"
        for line in normalised.splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]
    runs = [key for i, key in enumerate(keys) if i == 0 or keys[i - 1] != key]
    assert len(runs) == len(set(runs))

    # The workaround is only justified while Meeko still refuses the raw text,
    # so assert the refusal instead of assuming it.
    from meeko import Polymer

    with pytest.raises(ValueError, match="interrupted residues"):
        Polymer.from_pdb_string(split)


@requires_samples
def test_deleting_a_flexible_residue_is_reported() -> None:
    options = ReceptorPrepOptions(flexible_residues=("A:9999",))
    result = prepare_receptor(REFERENCE_PDB, options)

    assert result.report.flexible_residues == ["A:9999"]
    assert any("not in the structure" in warning for warning in result.report.warnings)


@requires_samples
def test_a_flexible_residue_produces_a_separate_flex_file() -> None:
    """A flexible residue keeps its backbone rigid and moves its sidechain out.

    Meeko splits the residue at the CA-CB bond: the backbone stays in the rigid
    file, the sidechain goes into the flex file wrapped in BEGIN_RES/END_RES.
    """
    full_atoms = parse_pdbqt(prepare_receptor(REFERENCE_PDB).pdbqt).first_pose.n_atoms
    result = prepare_receptor(REFERENCE_PDB, ReceptorPrepOptions(flexible_residues=("A:315",)))

    assert result.flex_pdbqt is not None
    assert result.flex_pdbqt.startswith("BEGIN_RES THR A 315")
    assert "END_RES THR A 315" in result.flex_pdbqt
    assert "ROOT" in result.flex_pdbqt

    rigid = parse_pdbqt(result.pdbqt).first_pose
    flex = parse_pdbqt(result.flex_pdbqt).first_pose

    # Nothing is lost or duplicated: the two files partition the receptor.
    assert flex.n_atoms > 0
    assert rigid.n_atoms + flex.n_atoms == full_atoms
    assert flex.n_atoms == 5  # CA, CB, CG2, HG1, OG1

    # The sidechain moved; a torsion tree was built for it.
    assert {atom.name for atom in flex.atoms} == {"CA", "CB", "CG2", "HG1", "OG1"}
    assert flex.rotatable_bonds == 2
    # The backbone stayed behind.
    backbone = {atom.name for atom in rigid.atoms if atom.resid == 315 and atom.chain == "A"}
    assert {"N", "C", "O"} <= backbone
    assert "CB" not in backbone


@requires_samples
def test_deleting_waters_and_hetero_is_reported() -> None:
    text = REFERENCE_PDB.read_text()
    # Append a water and an ion so the strip is observable.
    text += (
        "HETATM 9001  O   HOH B 601      10.000  10.000  10.000  1.00  0.00           O\n"
        "HETATM 9002 ZN    ZN B 602      11.000  10.000  10.000  1.00  0.00          ZN\n"
    )
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "with_water.pdb"
        path.write_text(text)
        result = prepare_receptor(path)

    assert result.report.deleted_waters == ["B:601"]
    assert result.report.deleted_hetero == ["B:602"]
    # Stripped residues must not appear in the output.
    assert "B:601" not in result.report.ignored_residues


# --------------------------------------------------------------------------
# rejections
# --------------------------------------------------------------------------


def test_a_prepared_pdbqt_is_not_reparameterised(tmp_path: Path) -> None:
    path = tmp_path / "already.pdbqt"
    path.write_text("ATOM      1  C   UNL     1       0.000   0.000   0.000  1.00  0.00     0.000 C\n")

    with pytest.raises(UnsupportedFormatError, match="already PDBQT"):
        prepare_receptor(path)


def test_an_already_prepared_receptor_is_inspectable(tmp_path: Path) -> None:
    path = tmp_path / "already.pdbqt"
    path.write_text("ATOM      1  C   UNL     1       0.000   0.000   0.000  1.00  0.00     0.000 C\n")

    inspection = inspect_receptor(path)

    assert inspection.preparable is False
    assert inspection.atoms == 1
    assert any("used as the rigid receptor" in note for note in inspection.notes)


def test_mmcif_minimal_file_with_atom(tmp_path: Path) -> None:
    """A minimal valid mmCIF with atoms should be accepted for inspection."""
    path = tmp_path / "receptor.cif"
    path.write_text(MMCIF_SAMPLE)

    result = inspect_receptor(path)
    assert result.input_format == "cif"
    assert result.preparable is True
    assert result.atoms == 4  # N, CA, C, O
    assert result.residues == 1
    assert "ALA" in result.residue_names


def test_mmcif_empty_or_unparseable_cif(tmp_path: Path) -> None:
    """A .cif file with no parseable atoms should fail gracefully."""
    path = tmp_path / "empty.cif"
    path.write_text("data_test\n")

    with pytest.raises(PreparationError, match=r"mmCIF|conversion|no atoms"):
        prepare_receptor(path)

    # inspect_receptor should return 0 atoms for empty mmCIF
    result = inspect_receptor(path)
    assert result.atoms == 0
    assert result.input_format == "cif"


def test_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="file not found"):
        prepare_receptor(tmp_path / "absent.pdb")
    with pytest.raises(InvalidInputError, match="file not found"):
        inspect_receptor(tmp_path / "absent.pdb")


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "receptor.xyz"
    path.write_text("not a receptor\n")

    with pytest.raises(UnsupportedFormatError):
        inspect_receptor(path)
    with pytest.raises(UnsupportedFormatError):
        prepare_receptor(path)


def test_a_structure_with_no_usable_residues_fails_as_a_domain_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdb"
    path.write_text("HEADER    nothing\nEND\n")

    # It must surface one of this project's own errors, never a raw ValueError
    # the API layer cannot map onto a status code.
    with pytest.raises(VinaStudioError):
        prepare_receptor(path)
