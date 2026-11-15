"""Reusable provenance helpers: file hashes, environment and git identity.

The validation report and the CLI result share these facts, but not a second
copy of the hashing/version code. Callers choose whether paths are shown
relative to the repository (validation reports) or resolved absolutely (CLI
results), and whether a restricted dataset must be redacted.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def git_metadata(repo_root: Path = REPO_ROOT) -> dict[str, str | bool | None]:
    """Repository identity for a report, without treating scratch as source."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                ".",
                ":(exclude).commandcode",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return {
            "commit": commit.stdout.strip() if commit.returncode == 0 else None,
            "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def environment_info() -> dict[str, str]:
    """Versions that can change a docking result; unknown is reported as such."""
    from vinastudio import __version__

    versions: dict[str, str] = {
        "appVersion": str(__version__),
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpuCount": str(os.cpu_count() or 0),
    }
    for distribution in ("vina", "meeko", "rdkit", "numpy", "scipy", "gemmi"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "unknown"
    try:
        versions["posebusters"] = importlib.metadata.version("posebusters")
    except importlib.metadata.PackageNotFoundError:
        versions["posebusters"] = "not installed"
    git = git_metadata()
    versions["gitCommit"] = str(git.get("commit") or "unknown")
    versions["gitDirty"] = (
        "unknown" if git.get("dirty") is None else ("yes" if git["dirty"] else "no")
    )
    try:
        from vinastudio.core.engines import backend_report

        backend = backend_report()
        versions["engineBackend"] = str(backend.get("backend") or "unavailable")
        versions["engineReason"] = str(backend.get("reason") or "")
    except Exception:  # noqa: BLE001 - provenance must not hide a report
        versions["engineBackend"] = "unknown"
        versions["engineReason"] = "could not resolve backend"
    return versions


def display_path(
    path: Path,
    *,
    redact: bool = False,
    relative_to_root: bool = True,
) -> str:
    if redact:
        return "<local-restricted>"
    if relative_to_root:
        try:
            return str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            pass
    return str(path.resolve())


def file_info(
    path: Path,
    *,
    redact: bool = False,
    relative_to_root: bool = True,
) -> dict[str, Any]:
    """Path, size and SHA-256 for one input; missing files stay explicit."""
    if not path.is_file():
        return {
            "path": display_path(path, redact=redact, relative_to_root=relative_to_root),
            "exists": False,
        }
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "path": display_path(path, redact=redact, relative_to_root=relative_to_root),
        "exists": True,
        "format": path.suffix.lower().lstrip("."),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }
