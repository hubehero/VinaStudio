"""Workspace endpoints must reject input that would silently do the wrong thing.

An empty path resolved to the process CWD and an empty rename name kept the
old name, so the request "succeeded" while doing nothing or worse.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def restore_active_workspace():
    """Undo the module-level active-workspace switch a test may trigger."""
    from vinastudio.server.routers import workspace as ws_router

    previous = ws_router._active_workspace
    yield
    ws_router._active_workspace = previous


def test_init_refuses_an_empty_path(client) -> None:  # type: ignore[no-untyped-def]
    body = client.post("/api/workspace/init", json={"path": "", "name": "x"})
    assert body.status_code == 422
    assert "workspace path is required" in body.json()["detail"]


def test_set_refuses_an_empty_path(client) -> None:  # type: ignore[no-untyped-def]
    body = client.post("/api/workspace/set", json={"path": "  "})
    assert body.status_code == 422


def test_rename_refuses_an_empty_name(
    client, restore_active_workspace, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/workspace/init", json={"path": str(tmp_path / "ws"), "name": "old"})

    body = client.put("/api/workspace/name", params={"name": ""})
    assert body.status_code == 422
    assert "workspace name is required" in body.json()["detail"]


def test_rename_strips_surrounding_space(
    client, restore_active_workspace, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/workspace/init", json={"path": str(tmp_path / "ws"), "name": "old"})

    body = client.put("/api/workspace/name", params={"name": "  new name  "})
    assert body.status_code == 200
    assert body.json()["name"] == "new name"


def test_migrate_reads_the_aliased_target_path(
    client, restore_active_workspace, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """The request model exposes ``target_path``; the router read ``targetPath``."""
    source = tmp_path / "src"
    client.post("/api/workspace/init", json={"path": str(source), "name": "src"})

    target = tmp_path / "moved"
    body = client.post("/api/workspace/migrate", json={"targetPath": str(target)})
    assert body.status_code == 200
    assert body.json()["path"] == str(target)
    assert (target / ".vinastudio.json").is_file()
