"""Integration tests for the loopback API surface the desktop shell relies on."""

from __future__ import annotations

import pytest


def test_health_reports_the_app_version(client) -> None:
    response = client.get("/api/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "VinaStudio"
    assert body["version"]
    assert body["uptimeSeconds"] >= 0


def test_system_info_reports_runtime_without_importing_heavy_modules(client) -> None:
    response = client.get("/api/system/info")
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["python"].startswith("3.")
    assert body["runtime"]["implementation"] == "CPython"
    # Metadata is read from installed distributions, so these must be present.
    assert set(body["packages"]) >= {"vina", "meeko", "rdkit", "numpy"}


def test_capabilities_describe_ad4_map_requirement(client) -> None:
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    body = response.json()

    by_name = {entry["name"]: entry for entry in body["scoringFunctions"]}
    assert set(by_name) == {"vina", "vinardo", "ad4"}
    assert by_name["vina"]["nativeMaps"] is True
    assert by_name["vinardo"]["nativeMaps"] is True
    # The UI gates AutoDock4 behind "load existing maps" using this flag.
    assert by_name["ad4"]["nativeMaps"] is False
    assert by_name["vina"]["weights"] == 7
    assert by_name["ad4"]["weights"] == 6

    # 3Dmol cannot parse PDBQT; the capability list must say so.
    assert "pdbqt" not in body["viewer"]["formats"]
    assert "sdf" in body["viewer"]["formats"]


def test_citations_are_listed(client) -> None:
    response = client.get("/api/system/citation")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) >= 2
    assert all(entry["doi"] for entry in entries)


def test_websocket_accepts_and_answers_pings(client) -> None:
    with client.websocket_connect("/ws") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["clients"] >= 1

        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}


def test_bundled_interface_is_served_when_present(client) -> None:
    from vinastudio.config import STATIC_DIR

    response = client.get("/")
    assert response.status_code == 200
    if (STATIC_DIR / "index.html").exists():
        assert "text/html" in response.headers["content-type"]
    else:
        # Falls back to an explanatory page rather than a 404.
        assert "Interface bundle missing" in response.text or "界面构建产物缺失" in response.text


@pytest.mark.slow
def test_selfcheck_imports_the_scientific_stack(client) -> None:
    """Actually imports vina, meeko and rdkit, so this is intentionally slow."""
    response = client.get("/api/system/selfcheck")
    assert response.status_code == 200
    body = response.json()

    by_name = {check["distribution"]: check for check in body["checks"]}
    for distribution in ("vina", "meeko", "rdkit"):
        check = by_name[distribution]
        assert check["importable"] is True, check["error"]
        assert check["importMs"] >= 0

    assert body["dockingAvailable"] is True
    assert body["failed"] == []
