"""The active workspace must survive a restart, and migration must stay contained.

Both are state-handling paths where a mistake is silent: an unreadable state file
looks like a first launch, and a migration into a subdirectory of the source
copies the destination into itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vinastudio.core.errors import InvalidInputError
from vinastudio.core.workspace import init_workspace, load_config, migrate_workspace


def _workspace(tmp_path: Path, name: str = "ws") -> Path:
    root = tmp_path / name
    init_workspace(root, name=name)
    return root


def test_state_file_lives_under_the_application_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path / "home"))
    from vinastudio.server.routers.workspace import _state_file

    assert _state_file() == tmp_path / "home" / "workspace.json"


def test_run_root_honours_the_application_home_without_an_active_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    """The fallback root used to hard-code ~/.vinastudio, so test runs (which
    redirect VINASTUDIO_HOME for isolation) wrote into the real home."""
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path / "home"))
    from vinastudio.core.paths import workspace_root
    from vinastudio.server.routers import workspace as ws

    monkeypatch.setattr(ws, "get_active_workspace", lambda: None)
    assert workspace_root() == tmp_path / "home" / "workspace"


def test_active_path_survives_a_round_trip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path / "home"))
    from vinastudio.server.routers import workspace as ws

    target = _workspace(tmp_path, "remembered")
    ws._save_active_path(target)

    assert ws._load_active_path() == target
    # Written through a temporary file, so nothing partial is left behind.
    assert not list((tmp_path / "home").glob("*.tmp"))
    assert json.loads(ws._state_file().read_text(encoding="utf-8")) == {"path": str(target)}


def test_unreadable_state_file_is_reported_not_treated_as_first_launch(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path / "home"))
    from vinastudio.server.routers import workspace as ws

    state = ws._state_file()
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{not json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        assert ws._load_active_path() is None
    assert "could not read" in caplog.text


def test_migration_refuses_a_target_inside_the_source(tmp_path: Path) -> None:
    source = _workspace(tmp_path, "source")

    with pytest.raises(InvalidInputError, match="must not be inside the source"):
        migrate_workspace(source, source / "nested")

    # Nothing was copied, and the source is untouched.
    assert not (source / "nested").exists()
    assert source.is_dir()


def test_migration_copies_the_directories_the_workspace_owns(tmp_path: Path) -> None:
    source = _workspace(tmp_path, "source")
    (source / "projects" / "example.vinaproj").write_text("{}", encoding="utf-8")

    migrate_workspace(source, tmp_path / "target")

    assert (tmp_path / "target" / "projects" / "example.vinaproj").is_file()
    assert load_config(tmp_path / "target").name == "source"
