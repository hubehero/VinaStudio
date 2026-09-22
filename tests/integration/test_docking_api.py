"""Integration tests for the docking API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.server.job_manager import JobState
from vinastudio.server.job_manager import manager as job_manager


@pytest.fixture(autouse=True)
def _reset_job_manager():
    """Ensure a clean job manager for each test."""
    job_manager._jobs.clear()
    yield


@pytest.fixture
def fake_receptor(tmp_path: Path) -> str:
    """Create a fake receptor file so file-existence checks pass."""
    rec = tmp_path / "rec.pdbqt"
    rec.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n")
    return str(rec)


@pytest.fixture
def fake_ligand(tmp_path: Path) -> str:
    """Create a fake ligand file so file-existence checks pass."""
    lig = tmp_path / "lig.pdbqt"
    lig.write_text("ATOM      1  CA  LIG A   1       0.000   0.000   0.000  1.00  0.00           C\n")
    return str(lig)


def test_get_defaults(client) -> None:
    from vinastudio.config import DEFAULTS

    body = client.get("/api/docking/defaults").json()
    # Both the documented numbers and the single source they must come from.
    assert body["scoring"] == DEFAULTS.scoring == "vina"
    assert body["exhaustiveness"] == DEFAULTS.exhaustiveness == 8
    assert body["nPoses"] == DEFAULTS.n_poses == 20
    assert body["minRmsd"] == DEFAULTS.min_rmsd == 1.0
    assert body["energyRange"] == DEFAULTS.energy_range == 3.0
    assert body["maxEvals"] == DEFAULTS.max_evals
    assert body["cpu"] == DEFAULTS.cpu
    assert body["seed"] == DEFAULTS.seed
    assert body["noRefine"] == DEFAULTS.no_refine
    assert body["verbosity"] == DEFAULTS.verbosity
    assert "weightCounts" in body
    assert body["weightCounts"]["vina"] == 7
    assert body["weightCounts"]["vinardo"] == 6
    assert body["weightCounts"]["ad4"] == 6


def test_cite_returns_the_method_it_names(client) -> None:
    expected = {
        "vina": ("vina", "Trott"),
        "vinardo": ("vinardo", "Quiroga"),
        "ad4": ("ad4", "Morris"),
    }

    for scoring, (function, author) in expected.items():
        body = client.get(f"/api/docking/cite?scoring={scoring}").json()
        # The endpoint exists so a user cites the right paper: a function name
        # that appears nowhere else and another method's citation would be worse
        # than returning nothing.
        assert body["function"] == function
        assert author in body["citation"]


def test_start_docking_missing_receptor(client) -> None:
    body = client.post(
        "/api/docking/start",
        json={
            "receptorPath": "/nonexistent/rec.pdbqt",
            "ligandPath": "/nonexistent/lig.pdbqt",
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
        },
    )
    assert body.status_code == 422
    assert "receptor" in body.json()["detail"].lower()


def test_start_docking_missing_ligand(client, fake_receptor: str) -> None:
    body = client.post(
        "/api/docking/start",
        json={
            "receptorPath": fake_receptor,
            "ligandPath": "/nonexistent/lig.pdbqt",
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
        },
    )
    assert body.status_code == 422
    assert "ligand" in body.json()["detail"].lower()


def test_list_jobs_empty(client) -> None:
    body = client.get("/api/docking/jobs").json()
    assert body == []


def test_get_job_not_found(client) -> None:
    body = client.get("/api/docking/jobs/nonexistent")
    assert body.status_code == 404


def test_cancel_job_not_found(client) -> None:
    body = client.post("/api/docking/jobs/nonexistent/cancel")
    assert body.status_code == 404


def test_result_not_completed(client) -> None:
    """Requesting results for a non-completed job returns 409."""
    state = JobState(job_id="test123", status="running", progress=50)
    job_manager._jobs["test123"] = state

    body = client.get("/api/docking/jobs/test123/result")
    assert body.status_code == 409


def test_result_completed(client) -> None:
    """Requesting results for a completed job returns the result."""
    state = JobState(
        job_id="done123",
        status="completed",
        progress=100,
        poses=[
            {"index": 1, "affinity": -8.5, "rmsdLower": 0.0, "rmsdUpper": 0.0},
            {"index": 2, "affinity": -7.2, "rmsdLower": 1.5, "rmsdUpper": 2.8},
        ],
        best_affinity=-8.5,
        n_poses=2,
        poses_pdbqt="REMARK VINA RESULT",
        poses_sdf="",
        elapsed_ms=5000,
    )
    job_manager._jobs["done123"] = state

    body = client.get("/api/docking/jobs/done123/result")
    assert body.status_code == 200
    data = body.json()
    assert data["status"] == "completed"
    assert data["bestAffinity"] == -8.5
    assert len(data["poses"]) == 2
    assert data["poses"][0]["affinity"] == -8.5


def test_cancel_running_job(client) -> None:
    """Cancelling a running job marks it as cancelled."""
    state = JobState(job_id="run123", status="running", progress=30)
    job_manager._jobs["run123"] = state

    body = client.post("/api/docking/jobs/run123/cancel")
    assert body.status_code == 200
    assert body.json()["status"] == "cancelled"

    status = client.get("/api/docking/jobs/run123").json()
    assert status["status"] == "cancelled"


def test_ad4_requires_maps(client, fake_receptor: str, fake_ligand: str) -> None:
    """ad4 scoring without mapPaths is rejected."""
    body = client.post(
        "/api/docking/start",
        json={
            "receptorPath": fake_receptor,
            "ligandPath": fake_ligand,
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
            "scoring": "ad4",
        },
    )
    assert body.status_code == 422
    assert "map" in body.json()["detail"].lower()


def test_score_rejects_scoring_without_native_maps(
    client, fake_receptor: str, fake_ligand: str
) -> None:
    """These endpoints compute their own maps, so ad4 cannot work here."""
    response = client.post(
        "/api/docking/score",
        json={
            "receptorPath": fake_receptor,
            "ligandPath": fake_ligand,
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
            "scoring": "ad4",
        },
    )

    assert response.status_code == 422
    assert "map" in response.json()["detail"].lower()


def test_score_reports_a_missing_ligand_file(client, fake_receptor: str, tmp_path: Path) -> None:
    """A bad ligand path is a validation error, not a failure inside the binding."""
    response = client.post(
        "/api/docking/score",
        json={
            "receptorPath": fake_receptor,
            "ligandPath": str(tmp_path / "absent.pdbqt"),
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
        },
    )

    assert response.status_code == 422
    assert "ligand file not found" in response.json()["detail"]


def test_job_list_after_start(client, fake_receptor: str, fake_ligand: str) -> None:
    """A started job appears in the jobs list."""
    body = client.post(
        "/api/docking/start",
        json={
            "receptorPath": fake_receptor,
            "ligandPath": fake_ligand,
            "center": [10.0, 20.0, 30.0],
            "size": [20.0, 20.0, 20.0],
        },
    )
    assert body.status_code == 200
    job_id = body.json()["jobId"]

    jobs = client.get("/api/docking/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == job_id
    assert jobs[0]["status"] in ("queued", "running", "completed")
