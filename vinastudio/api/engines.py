"""Stable adapter SDK imports for external engines."""

from __future__ import annotations

from vinastudio.core.engines.catalog import builtin_engines, doctor, inventory
from vinastudio.core.engines.contract import (
    EngineManifest,
    EngineResult,
    ExternalEngine,
    load_manifests,
)

__all__ = [
    "EngineManifest",
    "EngineResult",
    "ExternalEngine",
    "builtin_engines",
    "doctor",
    "inventory",
    "load_manifests",
]
