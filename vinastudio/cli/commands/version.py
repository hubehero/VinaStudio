"""``version``: software and engine versions without desktop imports."""

from __future__ import annotations

import argparse
from typing import Any

from vinastudio import __version__
from vinastudio.core.provenance import environment_info


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("version", help="show software and engine versions")
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    environment = environment_info()
    versions = {
        key: environment.get(key, "unknown")
        for key in ("vina", "meeko", "rdkit", "numpy", "scipy", "gemmi", "posebusters")
    }
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "version",
        "name": "vinastudio",
        "version": __version__,
        "python": environment.get("python", "unknown"),
        "backend": environment.get("engineBackend", "unknown"),
        "engineVersions": versions,
    }
    human = (
        f"vinastudio {__version__}\n"
        f"python: {payload['python']}\n"
        f"backend: {payload['backend']}\n"
        + "\n".join(f"{name}: {value}" for name, value in versions.items())
    )
    return payload, human
