"""Build the Vue interface into the Python package.

Vite writes straight to ``vinastudio/server/static`` (see ``web/vite.config.ts``),
so this script only has to install dependencies when needed and run the build.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
STATIC_DIR = REPO_ROOT / "vinastudio" / "server" / "static"

log = logging.getLogger("build_web")


def find_pnpm() -> str:
    """Locate pnpm, which ships outside the virtualenv in most setups."""
    for candidate in ("pnpm", "pnpm.cmd"):
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit(
        "pnpm was not found on PATH.\n"
        "Install it with:  corepack enable && corepack prepare pnpm@latest --activate\n"
        "or see https://pnpm.io/installation"
    )


def run(command: list[str], *, cwd: Path) -> None:
    log.info("$ %s", " ".join(command))
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip `pnpm install` (use when dependencies are already present).",
    )
    parser.add_argument("--typecheck", action="store_true", help="Run vue-tsc before building.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not WEB_DIR.is_dir():
        raise SystemExit(f"Interface sources missing: {WEB_DIR}")

    pnpm = find_pnpm()

    if not args.skip_install and not (WEB_DIR / "node_modules").is_dir():
        run([pnpm, "install"], cwd=WEB_DIR)

    if args.typecheck:
        run([pnpm, "run", "typecheck"], cwd=WEB_DIR)

    run([pnpm, "run", "build"], cwd=WEB_DIR)

    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise SystemExit(f"Build finished but {index} is missing")
    log.info("Interface built into %s", STATIC_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
