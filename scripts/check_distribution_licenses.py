#!/usr/bin/env python3
"""Check that shipped distributions carry the licence inventory."""

from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path

WHEEL_REQUIRED = (
    "vinastudio/LICENSE",
    "vinastudio/THIRD_PARTY_LICENSES.md",
    "vinastudio/licenses/Apache-2.0.txt",
    "vinastudio/licenses/LGPL-2.1.txt",
    "vinastudio/licenses/LGPL-3.0.txt",
    "vinastudio/licenses/RDKit-BSD.txt",
)


def check_wheel(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    return [name for name in WHEEL_REQUIRED if name not in names]


def check_deb(path: Path) -> list[str]:
    result = subprocess.run(
        ["dpkg-deb", "-c", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return [f"dpkg-deb could not read {path}: {result.stderr.strip()}"]
    names = result.stdout
    required = (
        "usr/share/doc/vinastudio/copyright",
        "usr/share/doc/vinastudio/LICENSE",
        "usr/share/doc/vinastudio/THIRD_PARTY_LICENSES.md",
    )
    missing = [name for name in required if name not in names]
    if "usr/share/doc/vinastudio/licenses/" not in names:
        missing.append("usr/share/doc/vinastudio/licenses/")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()

    failed = False
    for path in args.artifacts:
        suffix = path.suffix.lower()
        if suffix == ".whl":
            missing = check_wheel(path)
        elif suffix == ".deb":
            missing = check_deb(path)
        else:
            print(f"SKIP {path} (expected .whl or .deb)")
            continue
        if missing:
            failed = True
            print(f"FAIL {path}: missing {', '.join(missing)}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
