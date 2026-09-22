"""Saying what a file is must not depend on the extension that named it.

`.pdb` and `.pdbqt` are used for both receptors and ligands, so the answer has to
come from the file. These tests pin the rule against the reference structures and
against the case that used to misfile: a small molecule carrying waters.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.detect import detect_kind
from vinastudio.core.errors import InvalidInputError

SAMPLE = SAMPLE_DIR / "1iep"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
RECEPTOR_PDBQT = SAMPLE / "1iep_receptor.pdbqt"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"
POSES_PDBQT = SAMPLE / "1iep_ligand_vina_out.pdbqt"

requires_samples = pytest.mark.skipif(
    not all(
        path.exists()
        for path in (
            RECEPTOR_PDB,
            RECEPTOR_PDBQT,
            LIGAND_SDF,
            LIGAND_PDBQT,
            POSES_PDBQT,
        )
    ),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _pdb_line(
    serial: int, name: str, resname: str, resid: int, x: float, y: float, z: float, element: str
) -> str:
    return (
        f"ATOM  {serial:>5} {name:<4} {resname:>3} A{resid:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {element:>2}"
    )


def _het_line(serial: int, name: str, resname: str, resid: int, x: float, y: float, z: float) -> str:
    return (
        f"HETATM{serial:>5} {name:<4} {resname:>3} A{resid:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00           O"
    )


def test_extension_answers_for_unambiguous_formats(tmp_path: Path) -> None:
    for name, expected in [("ligand.sdf", "ligand"), ("ligand.mol", "ligand"),
                           ("receptor.cif", "receptor"), ("receptor.mmcif", "receptor")]:
        path = tmp_path / name
        path.write_text("data_x\n", encoding="utf-8")

        detection = detect_kind(path)

        assert detection.kind == expected
        assert detection.reason == "extension"


@requires_samples
def test_receptors_are_read_from_a_protein_shaped_file() -> None:
    for path in (RECEPTOR_PDB, RECEPTOR_PDBQT):
        detection = detect_kind(path)

        assert detection.kind == "receptor"
        assert detection.reason == "polymer residues"
        assert detection.polymer_residues >= 2


@requires_samples
def test_ligands_are_read_from_files_that_say_nothing() -> None:
    for path in (LIGAND_PDBQT, POSES_PDBQT):
        detection = detect_kind(path)

        assert detection.kind == "ligand"
        assert detection.reason == "small molecule"


def test_a_small_molecule_with_waters_is_not_a_receptor(tmp_path: Path) -> None:
    """The case the old frontend rule got wrong: one residue plus solvent."""
    path = tmp_path / "ligand_with_waters.pdb"
    path.write_text(
        "\n".join(
            [
                _pdb_line(1, "C1", "UNL", 1, 0.0, 0.0, 0.0, "C"),
                _pdb_line(2, "O1", "UNL", 1, 1.3, 0.0, 0.0, "O"),
                _het_line(3, "O", "HOH", 101, 5.0, 5.0, 5.0),
                _het_line(4, "O", "HOH", 102, 6.0, 5.0, 5.0),
            ]
        )
        + "\nEND\n",
        encoding="utf-8",
    )

    detection = detect_kind(path)

    assert detection.kind == "ligand"
    assert detection.residues == 3
    assert detection.waters == 2
    assert detection.polymer_residues == 1


def test_two_polymer_residues_are_a_receptor(tmp_path: Path) -> None:
    path = tmp_path / "small_protein.pdb"
    path.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", 1, 0.0, 0.0, 0.0, "C"),
                _pdb_line(2, "CA", "GLY", 2, 3.8, 0.0, 0.0, "C"),
            ]
        )
        + "\nEND\n",
        encoding="utf-8",
    )

    assert detect_kind(path).kind == "receptor"


def test_a_missing_file_is_a_validation_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="file not found"):
        detect_kind(tmp_path / "absent.pdb")


def test_an_unreadable_format_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="cannot tell what"):
        detect_kind(path)
