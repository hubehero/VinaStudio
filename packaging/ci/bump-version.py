#!/usr/bin/env python3
"""bump-version.py — Synchronize version across all VinaStudio project files.

Reads the canonical version from pyproject.toml (or accepts --version) and
updates every file that contains a hardcoded version string.

Usage:
    python packaging/ci/bump-version.py --version 0.2.0
    python packaging/ci/bump-version.py                 # reads pyproject.toml

Files updated:
    1. pyproject.toml               (canonical source)
    2. vinastudio/__init__.py       (fallback version, if hardcoded)
    3. vinastudio/config.py         (APP_VERSION, if hardcoded)
    4. web/package.json             (frontend version)
    5. packaging/linux/debian/control (debian package version)
    6. packaging/windows/vinastudio.iss (Inno Setup default VERSION)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_version_from_pyproject() -> str:
    """Extract the version string from pyproject.toml."""
    pyproject = REPO_ROOT / "pyproject.toml"
    text = pyproject.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        print("ERROR: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def validate_version(version: str) -> bool:
    """Check that the version looks like a valid PEP 440 / semver string."""
    return bool(re.match(r"^\d+\.\d+\.\d+([a-zA-Z0-9.+_-]*)?$", version))


def replace_in_file(path: Path, pattern: str, replacement: str, count: int = 1) -> bool:
    """Replace the first match of *pattern* in *path* with *replacement*.

    Returns True if a replacement was made.
    """
    if not path.exists():
        print(f"  SKIP  {path.relative_to(REPO_ROOT)} (not found)")
        return False

    text = path.read_text()
    # Use a function to check if replacement actually differs from match
    changes_made = False

    def _replacer(m: re.Match) -> str:
        nonlocal changes_made
        result = m.expand(replacement)
        if result != m.group(0):
            changes_made = True
        return result

    new_text = re.sub(pattern, _replacer, text, count=count)
    if not changes_made:
        print(f"  OK    {path.relative_to(REPO_ROOT)} (already up to date)")
        return False

    path.write_text(new_text)
    print(f"  OK    {path.relative_to(REPO_ROOT)} (updated)")
    return True


# ---------------------------------------------------------------------------
# Updaters
# ---------------------------------------------------------------------------

def update_pyproject(version: str) -> None:
    replace_in_file(
        REPO_ROOT / "pyproject.toml",
        r'^(version\s*=\s*)"[^"]+"',
        rf'\1"{version}"',
    )


def update_init_py(version: str) -> None:
    """Update vinastudio/__init__.py if it has a hardcoded fallback."""
    path = REPO_ROOT / "vinastudio" / "__init__.py"
    if not path.exists():
        return

    text = path.read_text()
    # Only replace if there's a hardcoded fallback like __version__ = "0.x.x"
    if re.search(r'__version__\s*=\s*"[^"]+"', text):
        replace_in_file(path, r'(__version__\s*=\s*)"[^"]+"', rf'\1"{version}"')
    else:
        print(f"  SKIP  vinastudio/__init__.py (no hardcoded version)")


def update_config_py(version: str) -> None:
    """Update vinastudio/config.py if APP_VERSION is hardcoded."""
    path = REPO_ROOT / "vinastudio" / "config.py"
    if not path.exists():
        return

    text = path.read_text()
    if "APP_VERSION" in text and re.search(r'APP_VERSION.*"[^"]+"', text):
        replace_in_file(path, r'(APP_VERSION\s*[:=].*?)"[^"]+"', rf'\1"{version}"')
    else:
        print(f"  SKIP  vinastudio/config.py (APP_VERSION not hardcoded)")


def update_package_json(version: str) -> None:
    path = REPO_ROOT / "web" / "package.json"
    if not path.exists():
        print(f"  SKIP  web/package.json (not found)")
        return

    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"  OK    web/package.json")


def update_debian_control(version: str) -> None:
    replace_in_file(
        REPO_ROOT / "packaging" / "linux" / "debian" / "control",
        r"^(Version:\s*)\S+",
        rf"\g<1>{version}",
    )


def update_inno_setup(version: str) -> None:
    replace_in_file(
        REPO_ROOT / "packaging" / "windows" / "vinastudio.iss",
        r'(#define\s+VERSION\s+")([^"]+)"',
        rf'\g<1>{version}"',
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize version across VinaStudio project files.",
    )
    parser.add_argument(
        "--version",
        help="Version string to set (e.g. 0.2.0). If omitted, reads from pyproject.toml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    args = parser.parse_args()

    # Determine the target version
    if args.version:
        version = args.version
    else:
        version = read_version_from_pyproject()

    if not validate_version(version):
        print(f"ERROR: '{version}' does not look like a valid version string", file=sys.stderr)
        sys.exit(1)

    print(f"Target version: {version}")
    if args.dry_run:
        print("(dry run — no files will be modified)\n")

    # Define the update sequence
    updaters = [
        ("pyproject.toml", update_pyproject),
        ("vinastudio/__init__.py", update_init_py),
        ("vinastudio/config.py", update_config_py),
        ("web/package.json", update_package_json),
        ("packaging/linux/debian/control", update_debian_control),
        ("packaging/windows/vinastudio.iss", update_inno_setup),
    ]

    # In dry-run mode, monkeypatch Path.write_text to be a no-op
    if args.dry_run:
        _real_write = Path.write_text

        def _noop_write(self, *a, **kw):  # noqa: ANN001, ANN002, ANN003
            return len(str(a[0])) if a else 0

        Path.write_text = _noop_write  # type: ignore[assignment]
        try:
            for label, updater in updaters:
                print(f"\n  [{label}]")
                try:
                    updater(version)
                except Exception as exc:
                    print(f"  ERROR {label}: {exc}", file=sys.stderr)
        finally:
            Path.write_text = _real_write  # type: ignore[assignment]
    else:
        for label, updater in updaters:
            print(f"\n  [{label}]")
            try:
                updater(version)
            except Exception as exc:
                print(f"  ERROR {label}: {exc}", file=sys.stderr)

    print(f"\n==> Version set to {version}")
    print("    Remember to commit and tag: git tag v{0}".format(version))


if __name__ == "__main__":
    main()
