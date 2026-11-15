"""Built-in and external engine inventory for ``engines list|doctor``."""

from __future__ import annotations

from typing import Any

from vinastudio.core.engines import api_available, backend_report, cli_available
from vinastudio.core.engines.contract import ExternalEngine


def builtin_engines() -> list[dict[str, Any]]:
    selected = backend_report().get("backend")
    return [
        {
            "name": "vina",
            "kind": "builtin",
            "version": "vina (python)",
            "available": api_available(),
            "selected": selected == "vina",
            "capabilities": ["dock", "score", "rescore", "optimize", "randomize"],
            "license": "Apache-2.0",
            "namespace": "vina",
        },
        {
            "name": "vina-cli",
            "kind": "builtin",
            "version": "vina (cli)",
            "available": cli_available(),
            "selected": selected == "vina-cli",
            "capabilities": ["dock", "score", "rescore", "optimize", "randomize"],
            "license": "Apache-2.0",
            "namespace": "vina",
        },
    ]


def inventory(external: list[ExternalEngine]) -> list[dict[str, Any]]:
    return [*builtin_engines(), *(engine.probe() for engine in external)]


def doctor(external: list[ExternalEngine]) -> dict[str, Any]:
    engines = inventory(external)
    available = [engine["name"] for engine in engines if engine.get("available")]
    return {
        "ok": bool(available),
        "engines": engines,
        "available": available,
    }
