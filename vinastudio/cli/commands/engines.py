"""``engines list|doctor``: built-in backends and external manifests."""

from __future__ import annotations

import argparse
from typing import Any

from vinastudio.cli.errors import InputError


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("engines", help="list or probe docking engines")
    actions = parser.add_subparsers(dest="action", required=True)
    for name, handler in (("list", _list), ("doctor", _doctor)):
        child = actions.add_parser(name)
        child.add_argument(
            "--manifest",
            action="append",
            default=[],
            metavar="PATH",
            help="external engine manifest (repeatable)",
        )
        child.add_argument("--json", action="store_true")
        child.set_defaults(handler=handler)


def _external(paths: list[str]):
    from vinastudio.core.engines.contract import load_manifests

    try:
        return load_manifests(paths)
    except Exception as exc:
        raise InputError(str(exc)) from exc


def _list(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    from vinastudio.core.engines.catalog import inventory

    engines = inventory(_external(args.manifest))
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "engines",
        "engines": engines,
    }
    lines = ["NAME       KIND     AVAILABLE  NAMESPACE"]
    for engine in engines:
        lines.append(
            f"{engine['name']:<10} {engine['kind']:<8} "
            f"{'yes' if engine.get('available') else 'no':<10} {engine.get('namespace', '')}"
        )
    return payload, "\n".join(lines)


def _doctor(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    from vinastudio.core.engines.catalog import doctor

    result = doctor(_external(args.manifest))
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "engines",
        "exitCode": 0 if result["ok"] else 3,
        **result,
    }
    lines = []
    for engine in result["engines"]:
        status = "ok" if engine.get("available") else f"unavailable: {engine.get('reason', '')}"
        lines.append(f"{engine['name']}: {status}")
    return payload, "\n".join(lines)
