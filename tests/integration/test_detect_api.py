"""The classification endpoint, over the reference structures.

The unit tests pin the rule; these pin that it is reachable and that the answer
carries the evidence the interface shows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR

SAMPLE = SAMPLE_DIR / "1iep"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
RECEPTOR_PDBQT = SAMPLE / "1iep_receptor.pdbqt"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"

requires_samples = pytest.mark.skipif(
    not all(path.exists() for path in (RECEPTOR_PDB, RECEPTOR_PDBQT, LIGAND_SDF, LIGAND_PDBQT)),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _detect(client, path: Path):  # type: ignore[no-untyped-def]
    response = client.post("/api/files/detect", json={"path": str(path)})
    assert response.status_code == 200, response.text
    return response.json()


@requires_samples
@pytest.mark.parametrize(
    ("path", "kind", "reason"),
    [
        (RECEPTOR_PDB, "receptor", "polymer residues"),
        (RECEPTOR_PDBQT, "receptor", "polymer residues"),
        (LIGAND_PDBQT, "ligand", "small molecule"),
        (LIGAND_SDF, "ligand", "extension"),
    ],
)
def test_detection_matches_the_reference_data(client, path: Path, kind: str, reason: str) -> None:
    body = _detect(client, path)

    assert body["kind"] == kind
    assert body["reason"] == reason
    if reason != "extension":
        # A file that had to be read carries what the reading found; an extension
        # that answers on its own is not opened.
        assert body["atoms"] > 0


@requires_samples
def test_a_receptor_reports_the_residues_that_made_it_one(client) -> None:
    body = _detect(client, RECEPTOR_PDB)

    assert body["polymerResidues"] >= 2
    assert body["polymerResidues"] == body["residues"] - body["waters"]


def test_an_unknown_file_is_rejected(client, tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")

    response = client.post("/api/files/detect", json={"path": str(path)})

    assert response.status_code == 422
    assert "cannot tell what" in response.text


def test_a_missing_file_is_rejected(client, tmp_path: Path) -> None:
    response = client.post("/api/files/detect", json={"path": str(tmp_path / "absent.pdb")})

    assert response.status_code == 422
    assert "file not found" in response.text
