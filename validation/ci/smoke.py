#!/usr/bin/env python3
"""Public-release backend smoke.

The development tree owns the full 830-test suite. The release tree does not
ship ``tests/``, so this script checks the backend contract that a user actually
depends on: import, workspace initialisation, file detection, ligand
parameterisation, box arithmetic and the read-only diagnostic endpoint.

It deliberately does not launch Qt, download anything, or run a full docking
job. Run it from the repository root with the project environment:

    uv run python validation/ci/smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "vinastudio" / "resources" / "sample" / "1iep"
LIGAND = SAMPLE / "1iep_ligand.sdf"


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not LIGAND.is_file():
        _fail(f"committed sample missing: {LIGAND}")

    # Must happen before the config module resolves app home.
    temp_home = tempfile.mkdtemp(prefix="vinastudio-release-smoke-")
    os.environ["VINASTUDIO_HOME"] = temp_home

    from fastapi.testclient import TestClient

    from vinastudio.server.app import create_app

    workspace = Path(temp_home) / "workspace"
    with TestClient(create_app()) as client:
        health = client.get("/api/system/health")
        if health.status_code != 200 or health.json().get("status") != "ok":
            _fail(f"health: {health.status_code} {health.text}")

        init = client.post(
            "/api/workspace/init",
            json={"path": str(workspace), "name": "release smoke"},
        )
        if init.status_code != 200:
            _fail(f"workspace init: {init.status_code} {init.text}")

        detect = client.post("/api/files/detect", json={"path": str(LIGAND)})
        if detect.status_code != 200 or detect.json().get("kind") != "ligand":
            _fail(f"detect: {detect.status_code} {detect.text}")

        inspect = client.post("/api/ligand/inspect", json={"path": str(LIGAND)})
        body = inspect.json() if inspect.status_code == 200 else {}
        if body.get("atoms") != 69 or not body.get("preparable"):
            _fail(f"ligand inspect: {inspect.status_code} {inspect.text}")

        prepare = client.post("/api/ligand/prepare", json={"path": str(LIGAND)})
        body = prepare.json() if prepare.status_code == 200 else {}
        if body.get("report", {}).get("outputAtoms") != 40:
            _fail(f"ligand prepare: {prepare.status_code} {prepare.text}")

        box = client.post(
            "/api/box/metrics",
            json={
                "center": [15.19, 53.903, 16.917],
                "size": [20.0, 20.0, 20.0],
                "spacing": 0.375,
            },
        )
        body = box.json() if box.status_code == 200 else {}
        if body.get("voxels") != [54, 54, 54] or body.get("canWriteMaps") is not True:
            _fail(f"box metrics: {box.status_code} {box.text}")

        diagnostics = client.get("/api/system/diagnostics")
        if diagnostics.status_code != 200:
            _fail(f"diagnostics: {diagnostics.status_code} {diagnostics.text}")
        checks = {check["id"] for check in diagnostics.json().get("checks", [])}
        for required in ("workspace", "catalog", "engine", "dependencies", "disk"):
            if required not in checks:
                _fail(f"diagnostics missing check: {required}")

    print("release backend smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
