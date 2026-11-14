#!/usr/bin/env python3
"""Write a machine-readable provenance manifest for release assets.

The release workflow has already built the artifacts and written
``SHA256SUMS``; this manifest adds the tag, commit, workflow run and a
per-file hash in one JSON document. It is not a signature, but it makes a
release easier to audit and lets a reader verify the assets without scraping
the workflow log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_version(root: Path) -> str:
    import tomllib

    return str(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])


def collect_artifacts(dist: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(dist.iterdir()):
        if not path.is_file() or path.name == "BUILD-MANIFEST.json":
            continue
        artifacts.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return artifacts


def build_manifest(
    *,
    version: str,
    tag: str,
    commit: str,
    artifacts: list[dict[str, Any]],
    run_url: str = "",
    repository: str = "",
    built_at: str = "",
    python_version: str = "",
) -> dict[str, Any]:
    source_url = (
        f"https://github.com/{repository}/tree/{commit}" if repository and commit else ""
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": "VinaStudio",
        "version": version,
        "tag": tag,
        "commit": commit,
        "source": source_url,
        "workflowRun": run_url,
        "builtAt": built_at or datetime.now(UTC).isoformat(),
        "python": python_version,
        "checksums": "SHA256SUMS",
        "signing": "unsigned",
        "artifacts": artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("dist/BUILD-MANIFEST.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--version", default="")
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-url", default="")
    parser.add_argument("--built-at", default="")
    parser.add_argument("--python", default=os.environ.get("PYTHON_VERSION", ""))
    args = parser.parse_args(argv)

    if not args.dist.is_dir():
        parser.error(f"dist directory does not exist: {args.dist}")
    version = args.version or project_version(args.root)
    run_url = args.run_url
    if not run_url and os.environ.get("GITHUB_RUN_ID"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repository = args.repository
        if repository:
            run_url = f"{server}/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    manifest = build_manifest(
        version=version,
        tag=args.tag,
        commit=args.commit,
        artifacts=collect_artifacts(args.dist),
        run_url=run_url,
        repository=args.repository,
        built_at=args.built_at,
        python_version=args.python,
    )
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
