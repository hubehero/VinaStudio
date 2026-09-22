"""Unit tests for the docking schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vinastudio.config import SCORING_WEIGHT_COUNT
from vinastudio.schemas.docking import (
    DockingDefaultsResponse,
    DockingJobCreated,
    DockingJobStatus,
    DockingJobSummary,
    DockingRequest,
    RandomizeRequest,
)


def test_docking_request_defaults() -> None:
    req = DockingRequest(
        receptorPath="/tmp/rec.pdbqt",
        ligandPath="/tmp/lig.pdbqt",
        center=(10.0, 20.0, 30.0),
        size=(20.0, 20.0, 20.0),
    )
    assert req.scoring == "vina"
    assert req.exhaustiveness == 8
    assert req.nPoses == 20
    assert req.energyRange == 3.0
    assert req.minRmsd == 1.0
    assert req.maxEvals == 0
    assert req.cpu == 0
    assert req.seed == 0
    assert req.noRefine is False
    assert req.verbosity == 1
    assert req.spacing == 0.375
    assert req.forceEvenVoxels is False
    assert req.weights is None
    assert req.mapPaths is None


def test_docking_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DockingRequest(
            receptorPath="/tmp/rec.pdbqt",
            ligandPath="/tmp/lig.pdbqt",
            center=(10.0, 20.0, 30.0),
            size=(20.0, 20.0, 20.0),
            bogus=42,
        )


def test_docking_request_validates_ranges() -> None:
    with pytest.raises(ValidationError):
        DockingRequest(
            receptorPath="/tmp/rec.pdbqt",
            ligandPath="/tmp/lig.pdbqt",
            center=(10.0, 20.0, 30.0),
            size=(20.0, 20.0, 20.0),
            exhaustiveness=0,
        )
    with pytest.raises(ValidationError):
        DockingRequest(
            receptorPath="/tmp/rec.pdbqt",
            ligandPath="/tmp/lig.pdbqt",
            center=(10.0, 20.0, 30.0),
            size=(20.0, 20.0, 20.0),
            nPoses=0,
        )


def _randomize_body(**overrides: object) -> RandomizeRequest:
    body: dict[str, object] = {
        "receptorPath": "/tmp/rec.pdbqt",
        "ligandPdbqtString": "ATOM      1  C1  UNL     1       0.000   0.000   0.000  0.00  0.00     0.000 C",
        "center": (10.0, 20.0, 30.0),
        "size": (20.0, 20.0, 20.0),
    }
    body.update(overrides)
    return RandomizeRequest(**body)  # type: ignore[arg-type]


def test_randomize_request_carries_a_seed() -> None:
    """Randomisation is the one stochastic workbench call, so it needs a seed
    to be replayable (the maps stay required: Vina ranks ``maxSteps``
    candidate conformers by energy)."""
    assert _randomize_body().seed == 0
    assert _randomize_body().maxSteps == 10000
    assert _randomize_body(seed=42).seed == 42

    with pytest.raises(ValidationError):
        _randomize_body(seed=-1)


def test_docking_defaults_response() -> None:
    resp = DockingDefaultsResponse()
    assert resp.scoring == "vina"
    assert resp.exhaustiveness == 8
    assert resp.weightCounts == dict(SCORING_WEIGHT_COUNT)


def test_docking_job_created() -> None:
    job = DockingJobCreated(jobId="abc123", status="queued")
    assert job.jobId == "abc123"
    assert job.status == "queued"


def test_docking_job_status() -> None:
    status = DockingJobStatus(
        jobId="abc123",
        status="running",
        progress=42,
        stage="docking",
        log=["line1", "line2"],
        error=None,
        elapsedMs=5000,
    )
    assert status.progress == 42
    assert status.stage == "docking"
    assert len(status.log) == 2


def test_docking_job_summary() -> None:
    summary = DockingJobSummary(
        jobId="abc123",
        status="completed",
        progress=100,
        stage="done",
        scoring="vina",
        elapsedMs=3000,
    )
    assert summary.status == "completed"
    assert summary.scoring == "vina"
