"""Inspecting a file must leave behind something the viewport can draw.

The viewport cannot render PDBQT (no bond orders) or mmCIF, so a loaded molecule
is drawn from a converted copy. These tests pin that the copy exists, is servable
and is what the viewer can read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from vinastudio.config import SAMPLE_DIR
from vinastudio.core.chem.ligand_prep import read_mol

SAMPLE = SAMPLE_DIR / "1iep"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"
POSES_PDBQT = SAMPLE / "1iep_ligand_vina_out.pdbqt"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
RECEPTOR_PDBQT = SAMPLE / "1iep_receptor.pdbqt"

requires_samples = pytest.mark.skipif(
    not all(
        path.exists()
        for path in (LIGAND_SDF, LIGAND_PDBQT, POSES_PDBQT, RECEPTOR_PDB, RECEPTOR_PDBQT)
    ),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _renderable(client, path: Path, kind: str):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/files/renderable", json={"path": str(path), "kind": kind}
    )
    assert response.status_code == 200, response.text
    return response.json()


@requires_samples
def test_ligand_becomes_a_servable_sdf(client) -> None:  # type: ignore[no-untyped-def]
    artifacts = _renderable(client, LIGAND_SDF, "ligand")

    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "sdf"
    assert artifacts[0]["url"].startswith("/artifacts/")

    # The URL has to work, and what comes back has to be the same molecule with
    # its bond orders intact — that is the whole reason for a converted copy.
    served = client.get(artifacts[0]["url"])
    assert served.status_code == 200
    source_mol, _ = read_mol(LIGAND_SDF)
    copied = Chem.MolFromMolBlock(served.text, removeHs=False)
    assert copied is not None
    assert Chem.MolToSmiles(copied) == Chem.MolToSmiles(source_mol)


@requires_samples
def test_receptor_becomes_a_servable_pdb(client) -> None:  # type: ignore[no-untyped-def]
    artifacts = _renderable(client, RECEPTOR_PDB, "receptor")

    assert artifacts[0]["kind"] == "pdb"
    served = client.get(artifacts[0]["url"])
    assert served.status_code == 200
    assert any(line.startswith("ATOM") for line in served.text.splitlines())


@requires_samples
def test_pdbqt_receptor_is_converted_before_rendering(client) -> None:  # type: ignore[no-untyped-def]
    """PDBQT is never handed to the viewer; the copy drops the AutoDock columns."""
    artifacts = _renderable(client, RECEPTOR_PDBQT, "receptor")

    served = client.get(artifacts[0]["url"])
    assert served.status_code == 200
    # A PDB element column, not the AutoDock atom type.
    atom_lines = [line for line in served.text.splitlines() if line.startswith("ATOM")]
    assert atom_lines
    assert "OA" not in {line[76:].strip() for line in atom_lines}


@requires_samples
def test_pdbqt_ligand_is_rebuilt_as_sdf(client) -> None:  # type: ignore[no-untyped-def]
    """A ligand PDBQT has no bond orders, so the copy is rebuilt from its SMILES."""
    artifacts = _renderable(client, LIGAND_PDBQT, "ligand")

    assert artifacts[0]["kind"] == "sdf"
    served = client.get(artifacts[0]["url"])
    assert served.status_code == 200
    source_mol, _ = read_mol(LIGAND_SDF)
    copied = Chem.MolFromMolBlock(served.text.split("$$$$")[0], removeHs=False)
    assert copied is not None
    assert Chem.MolToSmiles(copied) == Chem.MolToSmiles(source_mol)


@requires_samples
def test_docking_output_yields_one_record(client) -> None:  # type: ignore[no-untyped-def]
    """A docking output holds one pose per model; the preview keeps the first."""
    artifacts = _renderable(client, POSES_PDBQT, "ligand")

    served = client.get(artifacts[0]["url"])
    assert served.status_code == 200
    assert served.text.count("$$$$") == 1


def test_renderable_rejects_a_mismatched_kind(client, tmp_path: Path) -> None:
    """A receptor file asked for as a ligand is a validation error, not a crash."""
    ligand = tmp_path / "not_a_ligand.cif"
    ligand.write_text("data_x\n", encoding="utf-8")

    response = client.post(
        "/api/files/renderable", json={"path": str(ligand), "kind": "ligand"}
    )

    assert response.status_code == 422


def test_renderable_reports_a_missing_file(client, tmp_path: Path) -> None:
    response = client.post(
        "/api/files/renderable",
        json={"path": str(tmp_path / "absent.sdf"), "kind": "ligand"},
    )

    assert response.status_code == 422
