"""Per-run working directories for preparation and docking artefacts.

Every preparation writes into its own directory under the active workspace's
``jobs/`` subdirectory.  That keeps ``write_poses``-style "refuse to
overwrite" behaviour harmless, makes a run reproducible after the fact, and
gives the interface a stable place to fetch large artefacts (a receptor PDB is
hundreds of kilobytes, which has no business travelling inside a JSON response).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def workspace_root() -> Path:
    """Root of all run directories — uses the active workspace jobs/ subdir."""
    from vinastudio.config import app_home
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    # The fallback must go through app_home(), which honours VINASTUDIO_HOME.
    # Hard-coding ~/.vinastudio here sent test runs (that redirect the variable
    # for isolation) into the user's real home directory.
    root = ws / "jobs" if ws is not None else app_home() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def slugify(text: str, *, fallback: str = "run", limit: int = 40) -> str:
    """Turn a filename into a filesystem-safe fragment."""
    slug = _SLUG_STRIP.sub("-", Path(text).stem.lower()).strip("-")
    return slug[:limit] or fallback


@dataclass(slots=True)
class Workspace:
    """A directory that belongs to one preparation or docking run."""

    path: Path
    run_id: str

    def file(self, name: str) -> Path:
        return self.path / name

    def write(self, name: str, content: str) -> Path:
        target = self.file(name)
        target.write_text(content, encoding="utf-8")
        return target

    def relative(self, target: Path) -> str:
        """Path relative to the workspace root, for building artefact URLs."""
        return target.relative_to(workspace_root()).as_posix()


def create_workspace(prefix: str, *, stamp: str | None = None) -> Workspace:
    """Create a fresh run directory, never reusing an existing one."""
    run_id = f"{stamp or time.strftime('%Y%m%d-%H%M%S')}-{slugify(prefix)}"
    path = workspace_root() / run_id
    suffix = 1
    while path.exists():
        path = workspace_root() / f"{run_id}-{suffix}"
        suffix += 1
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        # TOCTOU race: another process created it between exists() and mkdir().
        # Append another suffix and retry once.
        path = workspace_root() / f"{run_id}-{suffix}"
        path.mkdir(parents=True)
    return Workspace(path=path, run_id=path.name)


def resolve_within(root: Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` inside ``root``, refusing anything that escapes.

    An absolute ``candidate`` is accepted only when it already points inside
    ``root``; a relative one is joined to ``root`` first. Either way a ``..``
    segment can never leave ``root``, which is what callers rely on when the
    segment arrives from a URL or a request body.
    """
    base = Path(root).resolve()
    resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"path escapes {base}: {candidate}")
    return resolved


def resolve_artifact(relative: str) -> Path:
    """Resolve a path inside the workspace root, refusing escapes."""
    return resolve_within(workspace_root(), relative)
