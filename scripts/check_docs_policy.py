#!/usr/bin/env python3
"""Offline checks for public documentation consistency.

This is deliberately independent of the application stack so it can run in the
release Quality job and in release preflight without Qt, Vina or network.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _local_links(path: Path) -> list[tuple[str, Path]]:
    text = re.sub(r"`[^`]*`", "", path.read_text(encoding="utf-8"))
    links: list[tuple[str, Path]] = []
    for match in LINK.finditer(text):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        links.append((target, (path.parent / target).resolve()))
    return links


def check(root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    citation_match = re.search(r'^version:\s*"([^"]+)"', citation, re.M)
    if not version_match or not citation_match or version_match.group(1) != citation_match.group(1):
        errors.append("CITATION.cff version does not match pyproject.toml")

    release_path = root / ".github/workflows/release.yml"
    if not release_path.is_file():
        release_path = root / "vina_simple/.github/workflows/release.yml"
    release = release_path.read_text(encoding="utf-8")
    releasing = (root / "RELEASING.md").read_text(encoding="utf-8")
    for job in ("preflight", "build-linux", "build-windows", "create-release"):
        if job not in release:
            errors.append(f"release.yml is missing job {job}")
        if job not in releasing:
            errors.append(f"RELEASING.md is missing job {job}")

    for readme_name in ("README.md", "README.en.md"):
        text = (root / readme_name).read_text(encoding="utf-8")
        build = text.find("pnpm -C web build")
        sync = text.find("uv sync --extra dev")
        if build < 0 or sync < 0 or build > sync:
            errors.append(f"{readme_name}: expected pnpm web build before uv sync")

    files = list((root / "docs").rglob("*.md"))
    files += [root / name for name in ("README.md", "README.en.md", "CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md", "RELEASING.md", "validation/README.md")]
    for path in files:
        if not path.is_file():
            continue
        for target, resolved in _local_links(path):
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: broken link {target}")
    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(f"FAIL  {error}")
        return 1
    print("PASS  public documentation policy is consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
