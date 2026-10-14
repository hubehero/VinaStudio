#!/usr/bin/env python3
"""Release pre-flight — the checks that keep a release to community norms.

Run this **before tagging**; it also runs as a CI job, where a failure stops the
Release from being created (the build job is gated on it, so a non-compliant
release simply cannot ship).

    python packaging/ci/release-preflight.py                    # before tagging
    python packaging/ci/release-preflight.py --allow-published   # re-running an existing tag

In CI (the tag run) it runs with ``--allow-published``: by then the number is
frozen by the tag, and what a tag run can still get wrong is the *notes* — the
body, the public wording, the tracked tree, the identity and the workflow.

It starts by listing what is already published, because a release is a *delta
against the last one* and its number must be the next in sequence — not a
milestone label that drifted. Then it checks:

  1. published versions listed, newest first
  2. the version is the next one in sequence (no skipped numbers)
  3. CHANGELOG.md has a section for that version (the release body source)
  4. neither the notes nor the new commit messages carry internal workflow talk
  5. the public tree holds no internal files
  6. the release-specific files are intact and the version has one source
  7. the commit identity is the project's, never a personal address
  8. the workflow takes the body from CHANGELOG.md, not from the generator

Exit code 0 means "safe to tag". Every failure says what to fix.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

PROJECT_NAME = "VinaStudio"
PROJECT_IDENTITY_EMAIL = "vinastudio@example.com"
PROJECT_IDENTITY_NAME = "VinaStudio"

#: Workflow vocabulary that must never reach a public release page or changelog.
INTERNAL_MARKERS = (
    "TASK-",
    "exchange/",
    "STATUS.md",
    "PLAN.md",
    "AGENTS.md",
    "看板",
    "白名单",
    "收官",
    "同步主树",
    "里程碑",
    "运行清单",
)

#: Files that exist only in the development tree; shipping one leaks the process.
FORBIDDEN_TRACKED = (
    "exchange/",
    "STATUS.md",
    "PLAN.md",
    "AGENTS.md",
    "MANUAL_TESTING.md",
    "HANDOVER.md",
    "REVIEW.md",
    "ISSUES.md",
)
FORBIDDEN_TRACKED_EXACT = ("RANKING.md",)
#: False positives to ignore when matching FORBIDDEN_TRACKED as substrings.
FORBIDDEN_TRACKED_ALLOW = (
    "vinastudio/core/chem/preview.py",
    "web/src/components/StatusPill.vue",
)

failures: list[str] = []
notes: list[str] = []


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=REPO_ROOT, capture_output=True, text=True, check=check
    )


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32mPASS\033[0m  {label}" + (f" — {detail}" if detail else ""))


def bad(label: str, detail: str) -> None:
    failures.append(f"{label}: {detail}")
    print(f"  \033[31mFAIL\033[0m  {label} — {detail}")


def note(text: str) -> None:
    notes.append(text)
    print(f"  \033[33mNOTE\033[0m  {text}")


def project_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if match is None:
        raise SystemExit("ERROR: no version in pyproject.toml")
    return match.group(1)


def parse_version(text: str) -> tuple[int, int, int]:
    parts = text.lstrip("v").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SystemExit(f"ERROR: {text!r} is not a MAJOR.MINOR.PATCH version")
    return int(parts[0]), int(parts[1]), int(parts[2])


def published_releases() -> list[dict[str, str]]:
    """Already-published releases, newest first (empty when unavailable)."""
    result = run(
        "gh", "release", "list", "--limit", "50", "--json", "tagName,publishedAt,name"
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def changelog_section(version: str) -> str | None:
    """The CHANGELOG section for *version*, reusing the extractor CI uses."""
    from importlib.util import module_from_spec, spec_from_file_location

    if not CHANGELOG.is_file():
        return None
    path = Path(__file__).resolve().parent / "changelog-section.py"
    spec = spec_from_file_location("changelog_section", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise SystemExit(f"ERROR: cannot load {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.section_for(CHANGELOG.read_text(encoding="utf-8"), version)


def commits_since_last_release(candidate: tuple[int, int, int]) -> str:
    """Commit messages added since the newest tag *below* the candidate version.

    In CI the checked-out HEAD *is* the tag being released, so the candidate's own
    tag must not be treated as "the previous release" — that would scan an empty
    range and quietly skip the wording check.
    """
    previous: str | None = None
    for tag in run("git", "tag", "--sort=-v:refname").stdout.split():
        if not tag.startswith("v"):
            continue
        try:
            parsed = parse_version(tag)
        except SystemExit:
            continue
        if parsed < candidate:
            previous = tag
            break
    if previous is None:
        return run("git", "log", "--format=%B").stdout
    return run("git", "log", f"{previous}..HEAD", "--format=%B").stdout


def main() -> int:
    allow_published = "--allow-published" in sys.argv[1:]
    version = project_version()
    parsed = parse_version(version)
    print(f"{PROJECT_NAME} release pre-flight — candidate version {version}")
    if allow_published:
        print("(--allow-published: waives the sequence check when re-running an existing tag)")
    print()

    # 1. What is already published? This is the reference the release is a delta
    #    against, and the only defensible basis for the next number.
    print("[1] Published releases")
    releases = published_releases()
    published_versions: list[tuple[int, int, int]] = []
    if releases:
        for release in releases:
            tag = release.get("tagName", "")
            date = (release.get("publishedAt") or "")[:10]
            if not tag.startswith("v"):
                continue
            try:
                published_versions.append(parse_version(tag))
            except SystemExit:
                continue
            print(f"      {tag}  {date}  {release.get('name', '')}")
    else:
        tags = [tag for tag in run("git", "tag", "--sort=-v:refname").stdout.split() if tag.startswith("v")]
        for tag in tags:
            try:
                published_versions.append(parse_version(tag))
            except SystemExit:
                continue
            print(f"      {tag}  (from local tags — `gh` unavailable)")
        note("Could not read releases from GitHub; used local tags. Run `git fetch --tags` first if this looks stale.")
    if not published_versions:
        note("No previous release found — this is the first one, so any version is fine.")

    # 2. Sequence: the candidate must be exactly one bump after the newest.
    print("\n[2] Version sequence")
    latest = max(published_versions) if published_versions else None
    if latest is None:
        ok("no previous release to compare against")
    else:
        major, minor, patch = latest
        latest_text = ".".join(str(part) for part in latest)
        allowed = {
            (major, minor, patch + 1),      # patch release
            (major, minor + 1, 0),          # minor release
            (major + 1, 0, 0),              # major release
        }
        expected = ", ".join(
            ".".join(str(part) for part in candidate) for candidate in sorted(allowed)
        )
        if parsed in allowed:
            ok(f"{latest_text} → {version}", "next in sequence")
        elif allow_published and parsed == latest:
            # Re-running an existing tag: the number is already frozen by the tag,
            # so pass with a note instead of recording a failure.
            note(f"--allow-published: {version} is already tagged; sequence check waived")
            ok("sequence check waived", "--allow-published")
        elif parsed == latest:
            bad(
                "version sequence",
                f"{version} is already published — bump to one of {expected}. "
                "To rebuild an existing tag's artifacts, run with --allow-published.",
            )
        elif parsed < latest:
            bad(
                "version sequence",
                f"{version} is older than the published latest ({latest_text})",
            )
        else:
            bad(
                "version sequence",
                f"{version} skips past {latest_text} — expected one of {expected}. "
                "Version numbers follow the released sequence, not internal milestones; "
                "never skip a number.",
            )

    # 3. Notes: the release body comes from CHANGELOG.md.
    print("\n[3] Release notes")
    section = changelog_section(version)
    if section is None:
        bad(
            "CHANGELOG section",
            f"CHANGELOG.md has no '## [{version}]' section — the release body would be empty",
        )
    else:
        ok(f"CHANGELOG.md has a [{version}] section", f"{len(section.splitlines())} lines")

    # 4. Public wording: no internal workflow language.
    print("\n[4] Public wording")
    scanned: list[tuple[str, str]] = []
    if section:
        scanned.append(("CHANGELOG section", section))
    messages = commits_since_last_release(parsed)
    if messages.strip():
        scanned.append(("new commit messages", messages))
    offenders = [
        (where, marker)
        for where, text in scanned
        for marker in INTERNAL_MARKERS
        if marker in text
    ]
    if offenders:
        for where, marker in offenders:
            bad("internal wording", f"{where} contains {marker!r} — move it to the development tree")
    else:
        ok("notes and new commits are free of workflow vocabulary")

    # 5. The public tree holds no internal files.
    print("\n[5] Public tree")
    tracked = run("git", "ls-files").stdout.split()
    leaked = [
        path
        for path in tracked
        if path not in FORBIDDEN_TRACKED_ALLOW
        and (
            any(path.startswith(prefix) for prefix in FORBIDDEN_TRACKED)
            or path in FORBIDDEN_TRACKED_EXACT
        )
    ]
    if leaked:
        bad("internal files tracked", f"{len(leaked)} file(s): {leaked[:5]}")
    else:
        ok("no development-only files tracked", f"{len(tracked)} files")

    # 6. Release-specific files intact, version single-sourced.
    print("\n[6] Release metadata")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    checks = [
        ("tests/" in gitignore, ".gitignore still excludes tests/"),
        ("project_urls" in pyproject, "pyproject.toml keeps its project_urls"),
        (CHANGELOG.is_file(), "CHANGELOG.md present"),
    ]
    for passed, label in checks:
        (ok if passed else bad)(label, "" if passed else "a sync step overwrote it")

    # 7. Identity: a personal address must never enter public history.
    print("\n[7] Commit identity")
    name = run("git", "config", "--local", "user.name").stdout.strip()
    email = run("git", "config", "--local", "user.email").stdout.strip()
    if email != PROJECT_IDENTITY_EMAIL or name != PROJECT_IDENTITY_NAME:
        global_email = run("git", "config", "--global", "user.email").stdout.strip()
        bad(
            "public identity",
            f"local user is {name!r} <{email or 'unset'}>; expected "
            f"{PROJECT_IDENTITY_NAME!r} <{PROJECT_IDENTITY_EMAIL}>. "
            + (
                f"The global identity ({global_email}) would otherwise end up in public history."
                if global_email and global_email != email
                else "Set it with: git config --local user.email …"
            ),
        )
    else:
        ok("commit identity is the project's", f"{name} <{email}>")

    # 8. The workflow must not fall back to generated notes.
    print("\n[8] Workflow")
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    if "generate_release_notes" in workflow:
        bad(
            "generated notes",
            "release.yml still sets generate_release_notes — it needs pull requests to "
            "describe anything and otherwise publishes a blank page",
        )
    elif "body_path" not in workflow:
        bad("release body", "release.yml has no body_path — the notes would be empty")
    else:
        ok("release body comes from CHANGELOG.md")

    print()
    if failures:
        print(f"\033[31m{len(failures)} check(s) failed — do not tag.\033[0m")
        return 1
    print("\033[32mAll pre-flight checks passed — safe to tag.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
