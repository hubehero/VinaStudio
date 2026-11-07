"""Artifact bookkeeping shared by the preparation routers."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from vinastudio.core.paths import Workspace
from vinastudio.schemas.preparation import Artifact, RunInfo

#: URL prefix the application mounts the workspace directory on.
ARTIFACT_URL_PREFIX = "/artifacts"

ArtifactKind = Literal["pdbqt", "pdb", "sdf", "json", "log", "text"]


def artifact(
    workspace: Workspace,
    target: Path,
    *,
    kind: ArtifactKind,
    name: str | None = None,
) -> Artifact:
    """Describe a written file, including the URL the interface fetches it from."""
    return Artifact(
        name=name or target.name,
        path=str(target),
        url=f"{ARTIFACT_URL_PREFIX}/{workspace.relative(target)}",
        bytes=target.stat().st_size,
        kind=kind,
    )


def run_info(workspace: Workspace, *, cached: bool = False) -> RunInfo:
    return RunInfo(runId=workspace.run_id, directory=str(workspace.path), cached=cached)


def cached_artifacts(
    workspace: Workspace, entry: dict[str, object]
) -> list[Artifact] | None:
    """Rebuild the artifact list from a cache marker, or ``None`` if incomplete."""
    raw = entry.get("artifacts")
    if not isinstance(raw, list):
        return None
    result: list[Artifact] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        kind = item.get("kind")
        if not isinstance(name, str) or kind not in {"pdbqt", "pdb", "sdf"}:
            return None
        target = workspace.file(name)
        if not target.is_file():
            return None
        result.append(artifact(workspace, target, kind=kind))  # type: ignore[arg-type]
    return result
