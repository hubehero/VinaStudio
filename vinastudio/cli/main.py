"""``vinastudio-cli`` entry point and subcommand registration."""

from __future__ import annotations

import argparse

from vinastudio import __version__
from vinastudio.cli.commands import (
    dock,
    engines,
    export,
    prepare,
    screen,
    server,
    validate,
    version,
)
from vinastudio.cli.errors import classify
from vinastudio.cli.output import emit_error, emit_result

COMMANDS = (
    "prepare",
    "dock",
    "screen",
    "validate",
    "export",
    "engines",
    "server",
    "version",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vinastudio-cli",
        description="Headless VinaStudio: preparation, docking, screening and validation.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"vinastudio {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in (prepare, dock, screen, validate, export, engines, server, version):
        module.add_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", "")
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error(f"unknown command: {command}")
    try:
        payload, human = handler(args)
    except KeyboardInterrupt:
        error = classify(KeyboardInterrupt())
        emit_error(error, command, json_mode=getattr(args, "json", False))
        return error.exit_code
    except Exception as exc:  # noqa: BLE001 - the CLI boundary maps every failure
        error = classify(exc)
        emit_error(error, command, json_mode=getattr(args, "json", False))
        return error.exit_code
    emit_result(payload, human, json_mode=getattr(args, "json", False))
    return int(payload.get("exitCode", 0))


if __name__ == "__main__":
    raise SystemExit(main())
