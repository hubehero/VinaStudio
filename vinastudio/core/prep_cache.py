"""Local preparation cache: metadata, hit lookup, statistics and cleanup.

Preparation output already lives in a content-addressed ``jobs/<run>`` directory
through :func:`vinastudio.core.paths.create_workspace`.  This module adds the
missing completion marker and the settings needed to reuse that directory
without rerunning Meeko.  The directory location and artifact names stay
unchanged so artifact URLs and persisted molecule references remain valid.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vinastudio import __version__
from vinastudio.core.paths import (
    JOB_STATE_FILENAME,
    PREP_CACHE_MARKER,
    Workspace,
    workspace_root,
)

CACHE_FORMAT_VERSION = 1
CACHE_SETTINGS_FILENAME = "prep-cache.json"

#: Defaults are deliberately conservative: keep well-used preparations for a
#: month, and cap the cache at 100 entries unless the user chooses otherwise.
DEFAULT_AUTO_CLEANUP = True
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_ENTRIES = 100

_LOCK = threading.RLock()
_STRUCTURAL_DIRS = frozenset({"jobs", "projects", "libraries", "exports", "receptors", "ligands", "cache"})


@dataclass(slots=True)
class CacheSettings:
    auto_cleanup: bool = DEFAULT_AUTO_CLEANUP
    retention_days: int = DEFAULT_RETENTION_DAYS
    max_entries: int = DEFAULT_MAX_ENTRIES


@dataclass(slots=True)
class CacheEntry:
    run_id: str
    kind: str
    path: Path
    bytes: int
    last_used: float
    created: float
    protected: bool = False


def _settings_path() -> Path:
    from vinastudio.config import app_home

    return app_home() / CACHE_SETTINGS_FILENAME


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load_settings() -> CacheSettings:
    """Read cache policy from ``<app-home>/prep-cache.json``.

    A missing/corrupt settings file must never block preparation; invalid values
    fall back to the defaults rather than being trusted.
    """
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CacheSettings()
    if not isinstance(data, dict):
        return CacheSettings()
    auto = data.get("autoCleanup")
    retention = data.get("retentionDays")
    maximum = data.get("maxEntries")
    return CacheSettings(
        auto_cleanup=auto if isinstance(auto, bool) else DEFAULT_AUTO_CLEANUP,
        retention_days=(
            int(retention)
            if isinstance(retention, int) and 0 <= retention <= 3650
            else DEFAULT_RETENTION_DAYS
        ),
        max_entries=(
            int(maximum)
            if isinstance(maximum, int) and 1 <= maximum <= 100000
            else DEFAULT_MAX_ENTRIES
        ),
    )


def save_settings(settings: CacheSettings) -> CacheSettings:
    """Persist the cache policy atomically and return the validated value."""
    _atomic_write(
        _settings_path(),
        json.dumps(
            {
                "autoCleanup": settings.auto_cleanup,
                "retentionDays": settings.retention_days,
                "maxEntries": settings.max_entries,
            },
            indent=2,
        )
        + "\n",
    )
    return settings


def marker_path(workspace: Workspace) -> Path:
    return workspace.path / PREP_CACHE_MARKER


def _read_marker(directory: Path) -> dict[str, Any] | None:
    marker = directory / PREP_CACHE_MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("formatVersion") != CACHE_FORMAT_VERSION:
        return None
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return None
        name = artifact.get("name")
        if not isinstance(name, str) or not name or Path(name).name != name:
            return None
        if not (directory / name).is_file():
            return None
    return data


def save_entry(
    workspace: Workspace,
    *,
    kind: str,
    source: str,
    key: str,
    report: dict[str, Any],
    artifacts: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> None:
    """Write the completion marker after every artifact is on disk."""
    now = time.time()
    total = sum(int(item.get("bytes", 0)) for item in artifacts)
    data: dict[str, Any] = {
        "formatVersion": CACHE_FORMAT_VERSION,
        "appVersion": __version__,
        "kind": kind,
        "source": source,
        "key": key,
        "createdAt": now,
        "lastUsedAt": now,
        "bytes": total,
        "report": report,
        "artifacts": [
            {"name": item["name"], "kind": item["kind"], "bytes": int(item.get("bytes", 0))}
            for item in artifacts
        ],
        **(extra or {}),
    }
    _atomic_write(marker_path(workspace), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_entry(workspace: Workspace, *, kind: str, key: str) -> dict[str, Any] | None:
    """Return a complete cache entry for this key, or ``None`` on any mismatch."""
    with _LOCK:
        data = _read_marker(workspace.path)
        if (
            data is None
            or data.get("kind") != kind
            or data.get("key") != key
            or data.get("appVersion") != __version__
        ):
            return None
        # Touch the marker only after validation; the timestamp drives cleanup.
        data["lastUsedAt"] = time.time()
        with contextlib.suppress(OSError):
            _atomic_write(
                marker_path(workspace),
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            )
        return data


def _entry_bytes(directory: Path, marker: dict[str, Any]) -> int:
    total = 0
    for artifact in marker.get("artifacts", []):
        path = directory / str(artifact.get("name", ""))
        try:
            total += path.stat().st_size
        except OSError:
            return int(marker.get("bytes", 0))
    return total


def cache_entries(
    root: Path | None = None, protected: set[Path] | None = None
) -> list[CacheEntry]:
    """List complete cache entries; unmarked/legacy dirs are not cache entries."""
    base = root or workspace_root()
    protected_paths = {path.resolve() for path in (protected or ())}
    try:
        children = list(base.iterdir())
    except OSError:
        return []
    entries: list[CacheEntry] = []
    for directory in children:
        if not directory.is_dir() or directory.name in _STRUCTURAL_DIRS:
            continue
        # A cache marker must never turn a docking job into a deletion target.
        if (directory / JOB_STATE_FILENAME).exists():
            continue
        marker = _read_marker(directory)
        if marker is None:
            continue
        try:
            stat = directory.stat()
        except OSError:
            continue
        entries.append(
            CacheEntry(
                run_id=directory.name,
                kind=str(marker.get("kind", "unknown")),
                path=directory,
                bytes=_entry_bytes(directory, marker),
                last_used=float(marker.get("lastUsedAt", stat.st_mtime)),
                created=float(marker.get("createdAt", stat.st_mtime)),
                protected=directory.resolve() in protected_paths,
            )
        )
    return entries


def cache_stats(root: Path | None = None, protected: set[Path] | None = None) -> dict[str, Any]:
    entries = cache_entries(root, protected)
    now = time.time()
    return {
        "entries": len(entries),
        "bytes": sum(item.bytes for item in entries),
        "protectedEntries": sum(1 for item in entries if item.protected),
        "protectedBytes": sum(item.bytes for item in entries if item.protected),
        "oldestDays": (
            max((now - item.last_used) / 86400 for item in entries) if entries else None
        ),
    }


def cleanup(
    settings: CacheSettings,
    *,
    protected: set[Path] | None = None,
    root: Path | None = None,
    manual: bool = False,
) -> dict[str, Any]:
    """Delete unprotected cache entries.

    Automatic cleanup honours the retention window and LRU entry cap. Manual
    clear removes every unprotected entry immediately. Referenced preparation
    directories are always kept: cache cleanup must never break a manifest,
    project, Catalog row or library entry.
    """
    if not manual and not settings.auto_cleanup:
        return {"removed": 0, "bytes": 0, "skippedProtected": 0}

    with _LOCK:
        entries = cache_entries(root, protected)
        candidates = [item for item in entries if not item.protected]
        if not manual:
            cutoff = time.time() - settings.retention_days * 86400
            expired = [item for item in candidates if item.last_used < cutoff]
            candidates = expired
            remaining = [item for item in entries if not item.protected and item not in expired]
            if len(remaining) > settings.max_entries:
                by_age = sorted(remaining, key=lambda item: item.last_used)
                candidates.extend(by_age[: len(remaining) - settings.max_entries])
        removed = 0
        freed = 0
        for entry in candidates:
            try:
                shutil.rmtree(entry.path)
            except OSError:
                continue
            removed += 1
            freed += entry.bytes
        return {
            "removed": removed,
            "bytes": freed,
            "skippedProtected": sum(1 for item in entries if item.protected),
        }


def release_directories(
    directories: set[Path], *, protected: set[Path] | None = None
) -> int:
    """Drop explicit cache directories that are complete and unreferenced.

    Used by "cancel preparation", where the caller already removed the catalog
    rows.  A directory with no marker is not a cache entry and is left alone;
    a protected directory still serves another persisted reference.
    """
    protected_paths = {path.resolve() for path in (protected or ())}
    removed = 0
    with _LOCK:
        for directory in directories:
            if not (directory / PREP_CACHE_MARKER).is_file():
                continue
            if directory.resolve() in protected_paths:
                continue
            try:
                shutil.rmtree(directory)
            except OSError:
                continue
            removed += 1
    return removed
