"""System information, dependency self-check and capability matrix."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from typing import Any

import certifi
from fastapi import APIRouter, Request

from vinastudio import __version__
from vinastudio.config import (
    APP_NAME,
    LIGAND_INPUT_SUFFIXES,
    NATIVE_MAP_SCORING,
    RECEPTOR_INPUT_SUFFIXES,
    SCORING_WEIGHT_COUNT,
    app_home,
    max_upload_bytes,
)
from vinastudio.core.diagnostics import repair_diagnostics, run_diagnostics
from vinastudio.core.engines import backend_report
from vinastudio.schemas.diagnostics import DiagnosticReport

log = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

#: Update checks are user-initiated and only ever point at the official releases
#: page. The repository is a constant, never user input, so the endpoint cannot
#: be turned into an arbitrary-URL fetch.
UPDATE_REPOSITORY = "hubehero/VinaStudio"
UPDATE_RELEASES_URL = f"https://github.com/{UPDATE_REPOSITORY}/releases"
UPDATE_LATEST_API = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
UPDATE_TIMEOUT_SECONDS = 5.0
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)

#: Distributions worth reporting in the UI, mapped to the module to import.
TRACKED_PACKAGES: dict[str, str] = {
    "vina": "vina",
    "meeko": "meeko",
    "rdkit": "rdkit",
    "numpy": "numpy",
    "scipy": "scipy",
    "PySide6": "PySide6",
}

#: Python libraries docking cannot run without. The engine itself is deliberately
#: absent: it is either the ``vina`` module *or* the shipped ``vina`` binary, so
#: an unimportable module is the normal state of a packaged Windows build rather
#: than a missing capability (``core.engines.backend_report`` answers the engine
#: question by itself).
DOCKING_LIBRARIES: tuple[str, ...] = ("meeko", "rdkit")


def _docking_verdict(failed: list[str], backend: str | None) -> dict[str, Any]:
    """Can docking run, and which library imports (if any) block it.

    ``failed`` is the raw self-check result, which legitimately names packages
    that docking does not need — reporting those as "missing dependencies" told
    CLI-backed users their working installation was broken.
    """
    missing = [name for name in DOCKING_LIBRARIES if name in failed]
    return {
        "dockingAvailable": backend is not None and not missing,
        "dockingMissing": missing,
    }


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except PackageNotFoundError:
        return None


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    """Parse the numeric ``major.minor.patch`` prefix of a release tag.

    Release tags are ``v0.4.1``; the comparison deliberately ignores a suffix
    such as ``-rc1`` because GitHub's ``/releases/latest`` endpoint already
    excludes prereleases. Returning ``None`` lets the endpoint report an
    invalid payload instead of guessing.
    """
    match = _VERSION_PATTERN.match(value.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _fetch_latest_release() -> dict[str, Any]:
    """Read the latest public GitHub release; the caller never passes a URL."""
    request = urllib.request.Request(
        UPDATE_LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{__version__}",
        },
    )
    # Start from the system trust store (which also covers corporate proxies),
    # then add the bundle shipped by certifi for frozen builds where the
    # interpreter has no default CA path. Passing only ``cafile`` would drop the
    # system certificates, which breaks TLS behind a proxy.
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    with urllib.request.urlopen(
        request, timeout=UPDATE_TIMEOUT_SECONDS, context=context
    ) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub release payload is not an object")
    return payload


def _update_error(exc: Exception) -> str:
    """Map transport failures to a small, translatable set of error codes."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return "no_release"
        if exc.code in (403, 429):
            return "rate_limited"
        return "unavailable"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        return "timeout" if isinstance(exc.reason, TimeoutError) else "offline"
    if isinstance(exc, ValueError):
        return "invalid_response"
    return "unavailable"


@router.get("/system/health")
def health(request: Request) -> dict[str, Any]:
    """Liveness probe used by the desktop shell and tests."""
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": __version__,
        "uptimeSeconds": round(time.time() - request.app.state.started_at, 3),
        "eventClients": request.app.state.events.client_count,
    }


@router.get("/system/info")
def info() -> dict[str, Any]:
    """Cheap environment summary: versions come from package metadata only."""
    return {
        "app": {"name": APP_NAME, "version": __version__},
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.system(),
            "platformRelease": platform.release(),
            "machine": platform.machine(),
        },
        "home": str(app_home()),
        "packages": {name: _distribution_version(name) for name in TRACKED_PACKAGES},
        # The desktop shell translates this env var into --disable-gpu before
        # Qt starts, so the frontend cannot read it itself — expose the ask
        # here so the UI can explain why rendering is slow.
        "rendering": {
            "softwareRenderRequested": os.environ.get("VINASTUDIO_SOFTWARE_RENDER") == "1"
        },
        # Which door the next docking run will use, and why. The two backends
        # share the engine but not the packaging, so "which one am I running" is
        # worth answering before a user wonders why a platform behaves oddly.
        "docking": backend_report(),
    }


@router.get("/system/selfcheck")
def selfcheck() -> dict[str, Any]:
    """Import the scientific stack for real and report what works.

    Importing ``vina`` and ``rdkit`` costs a second or two, so the result is
    cached for the lifetime of the process and the frontend calls this on
    demand rather than during startup.
    """
    checks: list[dict[str, Any]] = []
    for distribution, module_name in TRACKED_PACKAGES.items():
        entry: dict[str, Any] = {
            "distribution": distribution,
            "module": module_name,
            "version": _distribution_version(distribution),
        }
        started = time.perf_counter()
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - any import failure is the finding
            # The point of the self-check is to report *why* a dependency is
            # unusable (missing shared library, ABI mismatch, syntax error...),
            # so the exception type and text are captured verbatim.
            entry |= {"importable": False, "error": f"{type(exc).__name__}: {exc}"}
        else:
            entry |= {"importable": True, "error": None}
        entry["importMs"] = round((time.perf_counter() - started) * 1000)
        checks.append(entry)

    failed = [c["distribution"] for c in checks if not c["importable"]]
    return {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        **_docking_verdict(failed, backend_report()["backend"]),
    }


@router.get("/system/diagnostics", response_model=DiagnosticReport)
def diagnostics() -> DiagnosticReport:
    """Run safe, read-only installation checks.

    The active workspace is resolved lazily (the workspace router owns that
    state); this endpoint never creates or rewrites workspace data.
    """
    from vinastudio.server.routers.workspace import get_active_workspace

    return DiagnosticReport.model_validate(run_diagnostics(get_active_workspace()))


@router.post("/system/diagnostics/repair", response_model=DiagnosticReport)
def repair() -> DiagnosticReport:
    """Repair only missing application/workspace directories, then re-check.

    Corrupt configuration, catalogs and job indexes are intentionally not
    repaired here: replacing them would destroy the evidence the user needs.
    """
    from vinastudio.server.routers.workspace import get_active_workspace

    return DiagnosticReport.model_validate(repair_diagnostics(get_active_workspace()))


@lru_cache(maxsize=1)
def _capabilities() -> dict[str, Any]:
    return {
        "scoringFunctions": [
            {
                "name": "vina",
                "label": "Vina",
                "weights": SCORING_WEIGHT_COUNT["vina"],
                "nativeMaps": "vina" in NATIVE_MAP_SCORING,
                "notes": "Default force field; affinity maps are computed internally.",
            },
            {
                "name": "vinardo",
                "label": "Vinardo",
                "weights": SCORING_WEIGHT_COUNT["vinardo"],
                "nativeMaps": "vinardo" in NATIVE_MAP_SCORING,
                "notes": "Re-parameterised Vina force field, better for some targets.",
            },
            {
                "name": "ad4",
                "label": "AutoDock4",
                "weights": SCORING_WEIGHT_COUNT["ad4"],
                "nativeMaps": "ad4" in NATIVE_MAP_SCORING,
                "notes": (
                    "Requires affinity maps generated by AutoGrid4; loading existing "
                    "maps is supported, on-the-fly generation is not."
                ),
            },
        ],
        "ligandInputFormats": list(LIGAND_INPUT_SUFFIXES),
        "receptorInputFormats": list(RECEPTOR_INPUT_SUFFIXES),
        "outputFormats": [".pdbqt", ".sdf", ".csv", ".png", ".txt", ".json"],
        "viewer": {
            "engine": "3Dmol.js",
            "formats": ["pdb", "sdf", "mol2", "xyz", "pqr", "cif", "gro", "cube"],
            "note": "PDBQT is not renderable; poses are converted to SDF via Meeko.",
        },
        "languages": ["zh", "en"],
    }


@router.get("/system/capabilities")
def capabilities() -> dict[str, Any]:
    """Static description of what this build can do, for UI feature gating."""
    return _capabilities()


@router.get("/system/citation")
def citation() -> dict[str, Any]:
    """References the interface surfaces in its About dialog."""
    return {
        "entries": [
            {
                "title": "AutoDock Vina: improving the speed and accuracy of docking",
                "authors": "Trott, O., & Olson, A. J.",
                "venue": "Journal of Computational Chemistry, 31(2), 455-461",
                "year": 2010,
                "doi": "10.1002/jcc.21334",
            },
            {
                "title": (
                    "AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, "
                    "and Python Bindings"
                ),
                "authors": "Eberhardt, J., Santos-Martins, D., Tillack, A. F., & Forli, S.",
                "venue": "Journal of Chemical Information and Modeling, 61(8), 3891-3898",
                "year": 2021,
                "doi": "10.1021/acs.jcim.1c00203",
            },
            {
                "title": (
                    "Meeko: molecule parameterization and software interoperability "
                    "for docking and beyond"
                ),
                "authors": "Forli lab, CCSB at Scripps Research",
                "venue": "Journal of Chemical Information and Modeling",
                "year": 2025,
                "doi": "10.1021/acs.jcim.5c02271",
            },
        ]
    }


@router.get("/system/upload-limit")
def get_upload_limit() -> dict[str, Any]:
    """Return the current upload size limit in bytes and megabytes."""
    limit_bytes = max_upload_bytes()
    return {
        "bytes": limit_bytes,
        "megabytes": limit_bytes // (1024 * 1024),
    }


@router.get("/system/update-check")
def update_check() -> dict[str, Any]:
    """Compare this build with the latest public release.

    This is deliberately *not* called at startup: the user asks when they want
    it. The response is always HTTP 200 so an offline machine or a GitHub rate
    limit cannot break the settings dialog; ``error`` carries the machine-
    readable reason and the UI translates it. No download or install path exists
    here — the only action is opening the release page.
    """
    result: dict[str, Any] = {
        "current": __version__,
        "latest": None,
        "updateAvailable": False,
        "url": UPDATE_RELEASES_URL,
        "publishedAt": None,
        "error": None,
    }

    try:
        release = _fetch_latest_release()
    except Exception as exc:  # noqa: BLE001 - network failures must not break the app
        log.info("update check unavailable: %s", exc)
        result["error"] = _update_error(exc)
        return result

    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        result["error"] = "invalid_response"
        return result

    tag = tag.strip()
    latest = tag[1:] if tag[:1].lower() == "v" else tag
    result["latest"] = latest
    published = release.get("published_at")
    result["publishedAt"] = published if isinstance(published, str) else None

    current_version = _version_tuple(__version__)
    latest_version = _version_tuple(latest)
    if current_version is None or latest_version is None:
        result["error"] = "invalid_response"
        return result

    if latest_version > current_version:
        result["updateAvailable"] = True
        result["url"] = f"{UPDATE_RELEASES_URL}/tag/{urllib.parse.quote(tag, safe='')}"

    return result
