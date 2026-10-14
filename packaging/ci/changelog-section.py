#!/usr/bin/env python3
"""Print one version's section of ``CHANGELOG.md`` — the release body.

Usage:
    python packaging/ci/changelog-section.py 0.3.0 > release-notes.md

Exits non-zero when the version has no section. An empty release body is worse
than a failed build: it publishes a blank description to the public page, which
is exactly what we are avoiding by curating the changelog in the first place.

Section = from the ``## [...]`` heading of that version up to the next ``##``
heading (``###`` subheadings stay inside the section).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def section_for(text: str, version: str) -> str | None:
    """Return the changelog section for *version*, or None when it is absent."""
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(?:\s|$)")
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if heading.match(line):
            start = index
            break
    if start is None:
        return None

    collected: list[str] = []
    for line in lines[start:]:
        # The next version's heading ends this section; "###" subheadings are
        # part of it (and must not match: they are not "## " followed by space).
        if collected and line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).rstrip() + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("v")

    changelog = REPO_ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"ERROR: {changelog} not found", file=sys.stderr)
        return 1

    section = section_for(changelog.read_text(encoding="utf-8"), version)
    if section is None:
        print(
            f"ERROR: CHANGELOG.md has no section for {version} — add it before "
            "tagging, release notes are not generated automatically.",
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
