"""Integration tests for the search-box API."""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR

SAMPLE = SAMPLE_DIR / "1iep"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"

TUTORIAL_CENTER = [15.190, 53.903, 16.917]
TUTORIAL_SIZE = [20.0, 20.0, 20.0]

requires_samples = pytest.mark.skipif(
    not LIGAND_SDF.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)


def _spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {"center": TUTORIAL_CENTER, "size": TUTORIAL_SIZE}
    spec.update(overrides)
    return spec


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def test_metrics_match_vina_voxel_arithmetic(client) -> None:
    body = client.post("/api/box/metrics", json=_spec()).json()

    # ceil(20 / 0.375) == 54 voxels, and one more grid point than voxels.
    assert body["voxels"] == [54, 54, 54]
    assert body["gridPoints"] == [55, 55, 55]
    assert body["volume"] == 8000.0
    assert body["canWriteMaps"] is True
    assert body["warnings"] == []
    assert body["limits"] == [[5.19, 43.903, 6.917], [25.19, 63.903, 26.917]]


def test_an_odd_voxel_count_is_flagged_with_the_remedy(client) -> None:
    body = client.post(
        "/api/box/metrics", json=_spec(size=[7.875, 20.0, 30.0])
    ).json()

    assert body["voxels"][0] == 21
    assert body["canWriteMaps"] is False
    assert len(body["warnings"]) == 1
    assert "force_even_voxels" in body["warnings"][0]


def test_force_even_voxels_removes_the_warning(client) -> None:
    body = client.post(
        "/api/box/metrics",
        json=_spec(size=[7.875, 20.0, 30.0], forceEvenVoxels=True),
    ).json()

    assert body["voxels"][0] == 22
    assert body["canWriteMaps"] is True
    assert body["warnings"] == []


def test_a_huge_box_is_flagged_before_it_is_run(client) -> None:
    body = client.post("/api/box/metrics", json=_spec(size=[300, 300, 300])).json()

    assert any("million voxels" in warning for warning in body["warnings"])


@pytest.mark.parametrize(
    "spec",
    [
        _spec(size=[0.0, 20.0, 20.0]),
        _spec(size=[-5.0, 20.0, 20.0]),
        _spec(spacing=0.0),
    ],
)
def test_invalid_boxes_are_refused_with_a_domain_error(client, spec) -> None:
    response = client.post("/api/box/metrics", json=spec)

    assert response.status_code == 422
    assert response.json()["kind"] == "InvalidInputError"


def test_unknown_fields_are_refused(client) -> None:
    response = client.post("/api/box/metrics", json=_spec(surprise=1))
    assert response.status_code == 422


# --------------------------------------------------------------------------
# autobox
# --------------------------------------------------------------------------


@requires_samples
def test_autobox_from_the_ligand_reproduces_the_tutorial_centre(client) -> None:
    response = client.post(
        "/api/box/from-ligand", json={"path": str(LIGAND_SDF), "extend": 6.0}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["box"]["center"] == TUTORIAL_CENTER
    assert body["points"] == 37
    assert body["source"] == str(LIGAND_SDF)


@requires_samples
def test_autobox_extend_grows_each_edge_by_twice_the_margin(client) -> None:
    plain = client.post("/api/box/from-ligand", json={"path": str(LIGAND_SDF)}).json()
    grown = client.post(
        "/api/box/from-ligand", json={"path": str(LIGAND_SDF), "extend": 5.0}
    ).json()

    for axis in range(3):
        assert grown["box"]["size"][axis] == pytest.approx(
            max(plain["box"]["size"][axis], 0.375) + 10.0
        )
    assert grown["box"]["center"] == plain["box"]["center"]


@requires_samples
def test_autobox_from_a_residue_selection(client) -> None:
    whole = client.post(
        "/api/box/from-residues", json={"path": str(RECEPTOR_PDB), "residues": []}
    ).json()
    selection = client.post(
        "/api/box/from-residues",
        json={"path": str(RECEPTOR_PDB), "residues": ["A:315"]},
    ).json()

    assert selection["points"] < whole["points"]
    assert selection["box"]["volume"] < whole["box"]["volume"]
    assert selection["points"] > 0


@requires_samples
def test_a_selection_that_matches_nothing_names_the_residue(client) -> None:
    response = client.post(
        "/api/box/from-residues",
        json={"path": str(RECEPTOR_PDB), "residues": ["Z:9999"]},
    )

    assert response.status_code == 422
    assert "Z:9999" in response.json()["detail"]


@requires_samples
def test_hydrogens_can_be_included_on_request(client) -> None:
    heavy = client.post("/api/box/from-ligand", json={"path": str(LIGAND_SDF)}).json()
    full = client.post(
        "/api/box/from-ligand",
        json={"path": str(LIGAND_SDF), "includeHydrogens": True},
    ).json()

    assert heavy["points"] == 37
    assert full["points"] == 69
    assert full["box"]["volume"] > heavy["box"]["volume"]


def test_autobox_on_a_missing_file_is_a_domain_error(client, tmp_path: Path) -> None:
    response = client.post(
        "/api/box/from-ligand", json={"path": str(tmp_path / "gone.sdf")}
    )

    assert response.status_code == 422
    assert response.json()["kind"] == "InvalidInputError"


# --------------------------------------------------------------------------
# config.txt
# --------------------------------------------------------------------------


def test_config_round_trip_through_the_api(client) -> None:
    exported = client.post(
        "/api/box/to-config",
        json=_spec(forceEvenVoxels=True),
    ).json()["text"]

    assert "center_x = 15.190" in exported
    assert "force_even_voxels = 1" in exported

    reimported = client.post("/api/box/from-config", json={"text": exported}).json()
    assert reimported["center"] == TUTORIAL_CENTER
    assert reimported["forceEvenVoxels"] is True
    assert reimported["voxels"] == [54, 54, 54]


def test_config_import_accepts_a_whole_run_file(client) -> None:
    text = (
        "receptor = receptor.pdbqt\n"
        "ligand = ligand.pdbqt\n"
        "exhaustiveness = 32\n"
        "center_x = 15.190\ncenter_y = 53.903\ncenter_z = 16.917\n"
        "size_x = 20.0\nsize_y = 20.0\nsize_z = 20.0\n"
    )
    body = client.post("/api/box/from-config", json={"text": text}).json()

    assert body["center"] == TUTORIAL_CENTER


def test_a_config_without_a_box_is_refused(client) -> None:
    response = client.post("/api/box/from-config", json={"text": "exhaustiveness = 32\n"})

    assert response.status_code == 422
    assert "missing" in response.json()["detail"]
