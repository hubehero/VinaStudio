"""Build the Vue interface into the Python package.

Vite writes straight to ``vinastudio/server/static`` (see ``web/vite.config.ts``),
so this script only has to install dependencies when needed and run the build.
It also downloads Swagger UI assets for locally-served API docs.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
STATIC_DIR = REPO_ROOT / "vinastudio" / "server" / "static"

log = logging.getLogger("build_web")

SWAGGER_ASSETS = {
    "swagger-ui-bundle.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    "swagger-ui.css": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
}


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


def download_swagger_assets() -> None:
    """Download Swagger UI assets for locally-served API docs (no CDN at runtime)."""
    swagger_dir = STATIC_DIR / "swagger"
    swagger_dir.mkdir(exist_ok=True)
    for filename, url in SWAGGER_ASSETS.items():
        target = swagger_dir / filename
        if target.exists():
            log.info("swagger: %s already exists, skipping", filename)
            continue
        log.info("swagger: downloading %s", filename)
        try:
            urllib.request.urlretrieve(url, target)
            log.info("swagger: saved %s (%d bytes)", filename, target.stat().st_size)
        except Exception as exc:  # noqa: BLE001 - download failure must not abort the build
            log.warning("swagger: failed to download %s: %s", filename, exc)


def prune_stale_assets() -> None:
    """Delete hashed bundles the fresh ``index.html`` no longer references.

    Vite does not empty an outDir outside ``web/``, so every build leaves the
    previous ``index-*.js/css`` in place. A stale cached ``index.html`` would
    then keep running the old UI successfully instead of failing loudly, so
    only the assets the current index names may survive a build.
    """
    assets_dir = STATIC_DIR / "assets"
    index = STATIC_DIR / "index.html"
    if not assets_dir.is_dir() or not index.is_file():
        return
    referenced = set(re.findall(r'assets/([^"\'\s>]+)', index.read_text(encoding="utf-8")))
    for path in sorted(assets_dir.iterdir()):
        if path.is_file() and path.name not in referenced:
            log.info("pruning stale asset %s", path.name)
            path.unlink()


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

    download_swagger_assets()

    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise SystemExit(f"Build finished but {index} is missing")
    prune_stale_assets()
    log.info("Interface built into %s", STATIC_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
