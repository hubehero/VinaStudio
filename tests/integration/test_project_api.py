"""Path-valued request fields must stay inside the directories the app owns.

Both endpoints here take a filesystem path from the caller. ``delete_project``
receives it from a URL segment (where ``..`` survives), ``write_maps`` from the
request body. Neither may reach outside the directory that belongs to it.
"""

from __future__ import annotations

from pathlib import Path


def _projects_dir() -> Path:
    from vinastudio.server.routers.project import _get_projects_dir

    return _get_projects_dir()


def _save_project(client, name: str) -> Path:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/project/save", json={"filename": name, "project": {"name": name}}
    )
    assert response.status_code == 200, response.text
    return Path(response.json()["path"])


def test_delete_removes_a_project_inside_the_projects_directory(client) -> None:  # type: ignore[no-untyped-def]
    path = _save_project(client, "delete-me")

    response = client.delete("/api/project/delete-me.vinaproj")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert not path.exists()


def test_delete_refuses_a_name_that_escapes_the_projects_directory(client) -> None:  # type: ignore[no-untyped-def]
    # Whatever the active workspace is, resolve the decoy the same way the
    # endpoint would, so the test cannot pass by accident.
    target = (_projects_dir() / ".." / ".." / "escape-probe.vinaproj").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")

    # Percent-encoded separators are how the route actually receives them.
    response = client.delete("/api/project/..%2F..%2Fescape-probe.vinaproj")

    assert response.status_code == 422, response.text
    assert "invalid project name" in response.text
    assert target.exists(), "a project outside the projects directory was deleted"
    target.unlink()


def test_write_maps_refuses_a_prefix_outside_the_run_root(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    receptor = tmp_path / "receptor.pdbqt"
    receptor.write_text("REMARK test receptor\n", encoding="utf-8")
    outside_prefix = tmp_path / "maps" / "receptor"

    response = client.post(
        "/api/box/write-maps",
        json={
            "receptorPath": str(receptor),
            "center": (0.0, 0.0, 0.0),
            "size": (20.0, 20.0, 20.0),
            "outputPrefix": str(outside_prefix),
        },
    )

    assert response.status_code == 422, response.text
    assert not outside_prefix.parent.exists(), "maps were written outside the run root"
