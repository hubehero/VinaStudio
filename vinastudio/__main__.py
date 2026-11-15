"""Dispatch ``vinastudio`` between the headless CLI and the desktop shell.

Top-level imports stay minimal so ``vinastudio --help`` and
``import vinastudio.__main__`` do not pull in Qt or FastAPI.
"""

from __future__ import annotations

import sys

CLI_COMMANDS = (
    "prepare",
    "dock",
    "screen",
    "validate",
    "export",
    "engines",
    "server",
    "version",
)


def _desktop(argv: list[str]) -> int:
    try:
        from vinastudio.desktop.launcher import main as desktop_main

        return desktop_main(argv)
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] == "PySide6" or "PySide6" in str(exc):
            print(
                "The desktop interface is not installed; use "
                "`pip install vinastudio[desktop]` or `vinastudio-cli --help`.",
                file=sys.stderr,
            )
            return 2
        raise


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    first = args[0] if args else None
    if first in CLI_COMMANDS or first in {"--help", "-h", "--version"}:
        from vinastudio.cli.main import main as cli_main

        return cli_main(args)
    if first == "desktop":
        return _desktop(args[1:])
    return _desktop(args)


if __name__ == "__main__":
    raise SystemExit(main())
