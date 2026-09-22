"""Integration tests for the preparation API.

These check the HTTP contract the interface depends on: the shape of a report,
that artefacts are fetchable, and — most importantly — that a template failure
arrives as structured data rather than a bare message, because the UI offers to
exclude the offending residues and retry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR

SAMPLE = SAMPLE_DIR / "1iep"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
DOCKING_OUTPUT = SAMPLE / "1iep_ligand_vina_out.pdbqt"

requires_samples = pytest.mark.skipif(
    not LIGAND_SDF.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def test_filters_come_from_the_core_definitions(client) -> None:
    body = client.get("/api/files/filters").json()

    assert body["ligand"].startswith("Ligand files")
    assert ".sdf" in body["ligandSuffixes"]
    assert ".pdbqt" in body["receptorSuffixes"]


@requires_samples
def test_samples_are_listed_with_paths(client) -> None:
    samples = client.get("/api/files/samples").json()

    names = {entry["name"] for entry in samples}
    assert "1iep_receptorH.pdb" in names
    assert "1iep_ligand.sdf" in names
    for entry in samples:
        assert Path(entry["path"]).is_file()
        assert entry["bytes"] > 0


def test_upload_stores_a_dropped_file(client) -> None:
    content = b"ATOM      1  C   UNL     1       0.000   0.000   0.000  1.00  0.00     0.000 C\n"

    response = client.post(
        "/api/files/upload",
        files={"file": ("dropped.pdbqt", content, "chemical/x-pdbqt")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suffix"] == ".pdbqt"
    assert body["bytes"] == len(content)
    assert Path(body["path"]).read_bytes() == content


def test_upload_rejects_unsupported_and_empty_files(client) -> None:
    rejected = client.post(
        "/api/files/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert rejected.status_code == 415

    empty = client.post("/api/files/upload", files={"file": ("empty.sdf", b"", "text/plain")})
    assert empty.status_code == 400


# --------------------------------------------------------------------------
# ligand
# --------------------------------------------------------------------------


@requires_samples
def test_ligand_inspect_reports_the_preparation_work_todo(client) -> None:
    body = client.post("/api/ligand/inspect", json={"path": str(LIGAND_SDF)}).json()

    assert body["preparable"] is True
    assert body["inputFormat"] == "sdf"
    assert body["atoms"] == 69
    assert body["hydrogens"] == 32
    assert body["has3dCoordinates"] is True
    assert body["rotatableBonds"] == 7
    assert body["molecularFormula"] == "C29H32N7O+"


@requires_samples
def test_ligand_prepare_returns_report_artifacts_and_pdbqt(client) -> None:
    response = client.post("/api/ligand/prepare", json={"path": str(LIGAND_SDF)})
    assert response.status_code == 200
    body = response.json()

    report = body["report"]
    assert report["inputAtoms"] == 69
    assert report["outputAtoms"] == 40
    assert report["outputPolarHydrogens"] == 3
    assert report["rotatableBonds"] == 7
    assert report["totalCharge"] == pytest.approx(1.0, abs=0.05)
    assert report["warnings"] == []
    assert report["atomTypes"]["A"] > 0

    assert body["pdbqt"].startswith("REMARK SMILES")
    kinds = {entry["kind"] for entry in body["artifacts"]}
    assert kinds == {"pdbqt", "sdf"}


@requires_samples
def test_ligand_artifacts_are_fetchable(client) -> None:
    body = client.post("/api/ligand/prepare", json={"path": str(LIGAND_SDF)}).json()

    for entry in body["artifacts"]:
        response = client.get(entry["url"])
        assert response.status_code == 200
        assert len(response.text) == entry["bytes"]

    pdbqt_url = next(e["url"] for e in body["artifacts"] if e["kind"] == "pdbqt")
    assert client.get(pdbqt_url).text == body["pdbqt"]


@requires_samples
def test_ligand_options_reach_the_report(client) -> None:
    body = client.post(
        "/api/ligand/prepare",
        json={"path": str(LIGAND_SDF), "options": {"optimiseGeometry": False}},
    ).json()

    assert body["report"]["geometryOptimised"] is False


@requires_samples
def test_preparing_an_already_prepared_ligand_is_refused(client) -> None:
    response = client.post("/api/ligand/prepare", json={"path": str(LIGAND_PDBQT)})

    assert response.status_code == 422
    assert response.json()["kind"] == "UnsupportedFormatError"


def test_ligand_errors_carry_a_domain_kind(client, tmp_path: Path) -> None:
    missing = client.post("/api/ligand/prepare", json={"path": str(tmp_path / "absent.sdf")})
    assert missing.status_code == 422
    assert missing.json()["kind"] == "InvalidInputError"

    unreadable = tmp_path / "broken.sdf"
    unreadable.write_text("not a molecule\n")
    broken = client.post("/api/ligand/prepare", json={"path": str(unreadable)})
    assert broken.status_code == 422
    assert broken.json()["kind"] == "InvalidInputError"


# --------------------------------------------------------------------------
# receptor
# --------------------------------------------------------------------------


@requires_samples
def test_receptor_inspect_reports_the_construct(client) -> None:
    body = client.post("/api/receptor/inspect", json={"path": str(RECEPTOR_PDB)}).json()

    assert body["preparable"] is True
    assert body["chains"] == 1
    assert body["residues"] == 274
    assert body["waters"] == []
    assert body["hetero"] == []


@requires_samples
def test_receptor_prepare_returns_artifacts_but_not_inline_text(client) -> None:
    response = client.post("/api/receptor/prepare", json={"path": str(RECEPTOR_PDB)})
    assert response.status_code == 200
    body = response.json()

    report = body["report"]
    assert report["validResidues"] == 274
    assert report["normalisedAtomOrder"] is True
    assert report["atomTypes"]["HD"] > 400
    assert body["hasFlexibleSidechains"] is False
    # A receptor is too large to travel inside the JSON payload.
    assert "pdbqt" not in body
    assert {entry["kind"] for entry in body["artifacts"]} == {"pdbqt", "pdb"}


@requires_samples
def test_receptor_artifacts_are_fetchable(client) -> None:
    body = client.post("/api/receptor/prepare", json={"path": str(RECEPTOR_PDB)}).json()

    pdb_url = next(e["url"] for e in body["artifacts"] if e["kind"] == "pdb")
    response = client.get(pdb_url)
    assert response.status_code == 200
    assert response.text.startswith("ATOM")


@requires_samples
def test_flexible_residues_produce_a_flex_artifact(client) -> None:
    body = client.post(
        "/api/receptor/prepare",
        json={"path": str(RECEPTOR_PDB), "options": {"flexibleResidues": ["A:315"]}},
    ).json()

    assert body["hasFlexibleSidechains"] is True
    names = [entry["name"] for entry in body["artifacts"]]
    assert any(name.endswith("_flex.pdbqt") for name in names)
    flex_url = next(e["url"] for e in body["artifacts"] if e["name"].endswith("_flex.pdbqt"))
    assert client.get(flex_url).text.startswith("BEGIN_RES THR A 315")


@requires_samples
def test_template_failure_returns_the_offending_residues(client) -> None:
    """The UI needs the residue list to offer "exclude and retry"."""
    response = client.post(
        "/api/receptor/prepare",
        json={"path": str(RECEPTOR_PDB), "options": {"normaliseAtomOrder": False}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["kind"] == "ReceptorTemplateError"
    assert body["residues"] == ["A:438"]
    assert "contiguous" in body["detail"]


@requires_samples
def test_disabling_atom_normalisation_is_the_only_thing_that_fails(client) -> None:
    """Re-enabling it must let the same file through, or the workaround is useless."""
    ok = client.post(
        "/api/receptor/prepare",
        json={"path": str(RECEPTOR_PDB), "options": {"normaliseAtomOrder": True}},
    )
    assert ok.status_code == 200


@requires_samples
def test_receptor_errors_carry_a_domain_kind(client, tmp_path: Path) -> None:
    response = client.post("/api/receptor/prepare", json={"path": str(tmp_path / "gone.pdb")})
    assert response.status_code == 422
    assert response.json()["kind"] == "InvalidInputError"


# --------------------------------------------------------------------------
# contract hygiene
# --------------------------------------------------------------------------


def test_prepare_bodies_reject_unknown_fields(client) -> None:
    """Extra fields mean the caller is out of step with the API; say so."""
    for path in ("/api/ligand/prepare", "/api/receptor/prepare"):
        response = client.post(
            path, json={"path": "/tmp/x.sdf", "surprise": 1}
        )
        assert response.status_code == 422, path


@requires_samples
def test_artifacts_cannot_escape_the_workspace(client) -> None:
    for attempt in ("../config.py", "..%2fconfig.py", "%2e%2e/secret"):
        response = client.get(f"/artifacts/{attempt}")
        assert response.status_code in {400, 403, 404}, attempt
