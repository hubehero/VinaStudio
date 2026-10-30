"""Safe, user-triggered diagnostics for the local installation.

The diagnostic must answer three questions in order:

1. what is wrong?
2. can the application safely repair it without touching user data?
3. if it cannot, what should the user do next?

Only directory creation is automatic.  Configuration, catalogs, job indexes,
dependencies, engines and filesystem permissions are reported, never silently
rewritten or deleted: a corrupt catalog or job file is evidence, and a missing
scientific dependency needs an explicit installation decision.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vinastudio.config import app_home
from vinastudio.core.engines import backend_report

WORKSPACE_SUBDIRS: tuple[str, ...] = (
    "projects",
    "receptors",
    "ligands",
    "jobs",
    "exports",
    "libraries",
)
APP_SUBDIRS: tuple[str, ...] = ("cache", "logs", "projects")
MIN_FREE_BYTES = 512 * 1024 * 1024
LOW_FREE_BYTES = 128 * 1024 * 1024
MAX_JOB_INDEXES = 1000


def _check(
    check_id: str,
    severity: str,
    *,
    fixable: bool = False,
    detail: str | None = None,
    params: dict[str, Any] | None = None,
    suggestions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "severity": severity,
        "fixable": fixable,
        "detail": detail,
        "params": params or {},
        "suggestions": suggestions or [],
    }


def _rank(severity: str) -> int:
    return {"ok": 0, "warning": 1, "error": 2}.get(severity, 2)


def _worst(checks: list[dict[str, Any]]) -> str:
    return max((check["severity"] for check in checks), key=_rank, default="ok")


def _config_state(workspace: Path) -> tuple[str, str | None]:
    path = workspace / ".vinastudio.json"
    if not path.is_file():
        return "missing", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "invalid", f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return "invalid", "workspace config is not a JSON object"
    return "valid", None


def _catalog_check(workspace: Path) -> dict[str, Any]:
    path = workspace / "catalog.sqlite"
    if not path.is_file():
        return _check("catalog", "ok", detail="not initialised yet")
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
        result = str(row[0]) if row else "no result"
        if result.lower() != "ok":
            return _check(
                "catalog",
                "error",
                detail=result,
                suggestions=["rebuildCatalog"],
            )
        return _check("catalog", "ok", detail=str(path))
    except sqlite3.Error as exc:
        return _check(
            "catalog",
            "error",
            detail=f"{type(exc).__name__}: {exc}",
            suggestions=["backupAndRebuildCatalog"],
        )


def _jobs_check(workspace: Path) -> dict[str, Any]:
    jobs = workspace / "jobs"
    if not jobs.is_dir():
        return _check("jobs", "ok", detail="no jobs directory yet")
    invalid: list[str] = []
    indexes = sorted(jobs.glob("*/job.json"))[:MAX_JOB_INDEXES]
    for index in indexes:
        try:
            json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            invalid.append(f"{index}: {type(exc).__name__}: {exc}")
    if invalid:
        return _check(
            "jobs",
            "warning",
            detail="; ".join(invalid[:3]),
            params={"count": len(invalid), "scanned": len(indexes)},
            suggestions=["inspectJobIndexes"],
        )
    return _check("jobs", "ok", detail=f"{len(indexes)} job index(es) readable")


def _disk_check(home: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(home)
    except OSError as exc:
        return _check(
            "disk",
            "error",
            detail=f"{type(exc).__name__}: {exc}",
            suggestions=["checkDataDirectory"],
        )
    severity = "ok"
    suggestions: list[str] = []
    if usage.free < LOW_FREE_BYTES:
        severity = "error"
        suggestions = ["freeDiskSpace"]
    elif usage.free < MIN_FREE_BYTES:
        severity = "warning"
        suggestions = ["freeDiskSpace"]
    return _check(
        "disk",
        severity,
        detail=f"{usage.free / (1024 ** 3):.2f} GiB free",
        params={"freeBytes": usage.free},
        suggestions=suggestions,
    )


def _dependencies_check() -> dict[str, Any]:
    missing: list[str] = []
    for module in ("meeko", "rdkit", "gemmi"):
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(module)
    if missing:
        return _check(
            "dependencies",
            "error",
            detail=f"missing importable module(s): {', '.join(missing)}",
            params={"missing": missing},
            suggestions=["installDependencies"],
        )
    return _check("dependencies", "ok", detail="meeko, rdkit and gemmi are importable")


def _engine_check() -> dict[str, Any]:
    try:
        report = backend_report()
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic boundary
        return _check(
            "engine",
            "error",
            detail=f"{type(exc).__name__}: {exc}",
            suggestions=["installEngine"],
        )
    backend = report.get("backend")
    if not backend:
        return _check(
            "engine",
            "error",
            detail=str(report.get("reason") or "no docking backend available"),
            params={"reasonCode": report.get("reasonCode")},
            suggestions=["installEngine"],
        )
    return _check(
        "engine",
        "ok",
        detail=str(backend),
        params={
            "backend": backend,
            "reasonCode": report.get("reasonCode"),
        },
    )


def run_diagnostics(
    workspace: Path | None,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Run read-only checks and return a machine-readable report.

    ``workspace`` is the active workspace root (``None`` on first launch).
    The function does not create the workspace or its configuration; only
    ``repair_diagnostics`` performs safe directory creation.
    """
    home_path = (home or app_home()).expanduser()
    checks: list[dict[str, Any]] = []

    writable_home = home_path.is_dir() and os.access(home_path, os.W_OK)
    checks.append(
        _check(
            "app_home",
            "ok" if writable_home else "error",
            detail=str(home_path),
            suggestions=[] if writable_home else ["checkDataDirectory"],
        )
    )

    app_dirs = [name for name in APP_SUBDIRS if not (home_path / name).is_dir()]
    checks.append(
        _check(
            "app_dirs",
            "warning" if app_dirs else "ok",
            fixable=writable_home and bool(app_dirs),
            detail=", ".join(app_dirs),
            params={"missing": app_dirs},
            suggestions=["repairAppDirectories"] if app_dirs else [],
        )
    )

    if workspace is None:
        checks.append(
            _check(
                "workspace",
                "warning",
                detail="no active workspace",
                suggestions=["selectWorkspace"],
            )
        )
    else:
        ws = workspace.expanduser()
        exists = ws.is_dir()
        writable = exists and os.access(ws, os.W_OK)
        checks.append(
            _check(
                "workspace",
                "ok" if writable else "error",
                detail=str(ws),
                suggestions=[] if writable else ["selectWorkspace", "checkPermissions"],
            )
        )
        state, config_error = _config_state(ws) if exists else ("missing", None)
        if state == "valid":
            checks.append(_check("workspace_config", "ok", detail=str(ws / ".vinastudio.json")))
        else:
            checks.append(
                _check(
                    "workspace_config",
                    "error",
                    detail=config_error or "missing .vinastudio.json",
                    params={"state": state},
                    suggestions=["restoreWorkspaceConfig", "selectWorkspace"],
                )
            )

        missing_dirs = (
            [name for name in WORKSPACE_SUBDIRS if not (ws / name).is_dir()]
            if exists
            else []
        )
        checks.append(
            _check(
                "workspace_dirs",
                "warning" if missing_dirs else "ok",
                fixable=bool(missing_dirs) and state == "valid" and writable,
                detail=", ".join(missing_dirs),
                params={"missing": missing_dirs},
                suggestions=["repairWorkspaceDirectories"] if missing_dirs else [],
            )
        )
        checks.append(_catalog_check(ws) if exists else _check("catalog", "ok", detail="workspace unavailable"))
        checks.append(_jobs_check(ws) if exists else _check("jobs", "ok", detail="workspace unavailable"))

    checks.append(_engine_check())
    checks.append(_dependencies_check())
    checks.append(_disk_check(home_path))

    severity = _worst(checks)
    return {
        "ok": severity != "error",
        "severity": severity,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "workspace": str(workspace) if workspace is not None else None,
        "checks": checks,
        "repairAvailable": any(check["fixable"] for check in checks),
        "repaired": [],
    }


def repair_diagnostics(
    workspace: Path | None,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Apply only safe, idempotent directory repairs, then re-check.

    No user data is deleted, overwritten or migrated.  A corrupt configuration,
    catalog or job index is deliberately left in place until the user chooses a
    recovery action.
    """
    home_path = (home or app_home()).expanduser()
    repaired: list[str] = []

    for name in APP_SUBDIRS:
        target = home_path / name
        if not target.is_dir():
            try:
                target.mkdir(parents=True, exist_ok=True)
                repaired.append("app_dirs")
            except OSError:
                pass

    if workspace is not None:
        ws = workspace.expanduser()
        state, _ = _config_state(ws) if ws.is_dir() else ("missing", None)
        may_repair_workspace = (
            state == "valid" and os.access(ws, os.W_OK)
        )
        if may_repair_workspace:
            for name in WORKSPACE_SUBDIRS:
                target = ws / name
                if not target.is_dir():
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                        repaired.append("workspace_dirs")
                    except OSError:
                        pass

    report = run_diagnostics(workspace, home=home_path)
    report["repaired"] = sorted(set(repaired))
    return report
