"""System information, dependency self-check and capability matrix."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import os
import platform
import sys
import time
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from typing import Any

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
from vinastudio.core.engines import backend_report

log = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

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
