"""Fetch the official Vina command-line binary used by the CLI backend.

The Python module (`from vina import Vina`) has no Windows build and
conda-forge has no ``win-64`` build either, but upstream publishes Linux, Windows
and macOS (x86_64) binaries of the same 1.2.7 engine. The CLI backend drives those,
and this script is where they come from — pinned by name, URL and SHA-256, like
``fetch_samples.py`` does for the gold standard.

    uv run python scripts/fetch_vina_cli.py                # the current platform
    uv run python scripts/fetch_vina_cli.py --all          # every entry
    uv run python scripts/fetch_vina_cli.py --platform windows

Nothing here is committed: the binaries are gitignored, and the packaged builds
bundle them at build time.

Vina is Apache-2.0 (https://github.com/ccsb-scripps/AutoDock-Vina); redistribution
requires keeping its licence and notice, which is what ``resources/vina/README.md``
records.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import platform
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_ROOT / "vinastudio" / "resources" / "vina"

_RELEASE = "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7"

log = logging.getLogger("fetch_vina_cli")


@dataclass(frozen=True)
class Binary:
    """One official binary, pinned by hash."""

    platform: str
    filename: str
    sha256: str
    bytes: int
    url: str


#: Verified 2026-10-15 by downloading and hashing each file.
BINARIES: tuple[Binary, ...] = (
    Binary(
        platform="linux",
        filename="vina",
        sha256="f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644",
        bytes=4_056_088,
        url=f"{_RELEASE}/vina_1.2.7_linux_x86_64",
    ),
    Binary(
        platform="windows",
        filename="vina.exe",
        sha256="e0c4b2715e0c1a74f6e92d0f3be0328ac97542eafbc111e6b1efad897a73cce5",
        bytes=1_233_920,
        url=f"{_RELEASE}/vina_1.2.7_win.exe",
    ),
    Binary(
        platform="darwin",
        filename="vina",
        sha256="9f44ccbb163223613283a75d0be53235d9e63f4da08292cb7196144f9838b7f9",
        bytes=1_215_392,
        # x86_64 only: 1.2.7 publishes no arm64 asset, so Apple Silicon runs this
        # through Rosetta. Pinned like the others, but no macOS build has been
        # exercised — unlike Linux and Windows, there is no CI evidence behind it.
        url=f"{_RELEASE}/vina_1.2.7_mac_x86_64",
    ),
)


def current_platform() -> str:
    return platform.system().lower()


def existing(entry: Binary) -> bool:
    target = TARGET_DIR / entry.filename
    return target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry.sha256


def download(entry: Binary) -> bytes | None:
    """The pinned payload, or ``None`` with a logged reason. Never writes anything."""
    if not entry.sha256:
        log.warning("%s: no pinned hash — refusing to fetch it", entry.platform)
        return None

    log.info("%s: downloading %s", entry.filename, entry.url)
    try:
        # A pinned https URL from the table above, never a caller-supplied one.
        with urllib.request.urlopen(entry.url, timeout=120) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        log.error("%s: download failed: %s", entry.filename, exc)
        return None

    digest = hashlib.sha256(payload).hexdigest()
    if digest != entry.sha256:
        log.error(
            "%s: SHA-256 mismatch (expected %s, got %s) — refusing to install it",
            entry.filename, entry.sha256, digest,
        )
        return None
    if entry.bytes and len(payload) != entry.bytes:
        log.error("%s: size %d != pinned %d", entry.filename, len(payload), entry.bytes)
        return None

    log.info("%s: verified (%d bytes)", entry.filename, len(payload))
    return payload


def fetch(entry: Binary) -> bool:
    """Make this platform's binary present and verified."""
    if existing(entry):
        log.info("%s: already present and verified", entry.filename)
        return True

    payload = download(entry)
    if payload is None:
        return False

    target = TARGET_DIR / entry.filename
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    target.chmod(0o755)
    log.info("%s: installed (%d bytes)", entry.filename, len(payload))
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=[entry.platform for entry in BINARIES],
                        default=current_platform())
    parser.add_argument("--all", action="store_true", help="check every pinned binary")
    args = parser.parse_args()

    if args.all:
        # Check every pin, install only this platform's. Linux and macOS share the
        # target filename, so installing each in turn would leave whichever came
        # last in place — a foreign executable reporting itself as fetched.
        here = current_platform()
        failed = [
            entry.platform
            for entry in BINARIES
            if not (fetch(entry) if entry.platform == here else existing(entry) or bool(download(entry)))
        ]
    else:
        wanted = tuple(e for e in BINARIES if e.platform == args.platform)
        if not wanted:
            log.error("no binary listed for platform %r (have: %s)",
                      args.platform, ", ".join(e.platform for e in BINARIES))
            return 1
        failed = [entry.platform for entry in wanted if not fetch(entry)]

    if failed:
        log.error("not fetched: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
