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


def run_info(workspace: Workspace) -> RunInfo:
    return RunInfo(runId=workspace.run_id, directory=str(workspace.path))
