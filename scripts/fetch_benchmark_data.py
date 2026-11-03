#!/usr/bin/env python3
"""Fetch or verify open benchmark resources from pinned URLs.

The manifest's ``resources`` entries are the only files this tool touches:

    {
      "path": "open/1abc/1abc.pdb",
      "url": "https://files.rcsb.org/download/1ABC.pdb",
      "sha256": "..."
    }

It refuses a restricted dataset, absolute/parent-relative output paths, HTTP
errors and checksum mismatches. It never logs in, follows a registration form
or accepts a licence on the user's behalf. The default test suite does not call
this tool; a download is an explicit action.

Examples:
    uv run python scripts/fetch_benchmark_data.py \
      --manifest validation/benchmark/manifests/open-posebusters-v1.json \
      --out .benchmark-data

    uv run python scripts/fetch_benchmark_data.py \
      --manifest ... --out .benchmark-data --verify-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "validation" / "benchmark" / "manifests" / "open-posebusters-v1.json"
TIMEOUT = 60


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("manifest must be a JSON object")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise SystemExit("manifest has no dataset object")
    if dataset.get("redistributable") is not True:
        raise SystemExit("refusing to download a non-redistributable dataset")
    resources = payload.get("resources")
    if not isinstance(resources, list) or not resources:
        raise SystemExit("manifest has no resources list")
    return payload


def _safe_target(out_dir: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise SystemExit("resource path must be a non-empty string")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"resource path must stay inside the output directory: {relative!r}")
    target = (out_dir / candidate).resolve()
    root = out_dir.resolve()
    if target != root and root not in target.parents:
        raise SystemExit(f"resource path escapes output directory: {relative!r}")
    return target


def _check_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in value
    ):
        raise SystemExit(f"{label} needs a 64-character SHA-256")
    return value.lower()


def _verify_one(target: Path, expected: str) -> bool:
    if not target.is_file():
        print(f"MISSING {target}")
        return False
    actual = _sha256(target)
    if actual != expected:
        print(f"MISMATCH {target}: {actual} != {expected}")
        return False
    print(f"OK       {target}")
    return True


def _download(url: object, target: Path, expected: str) -> None:
    if not isinstance(url, str) or urlparse(url).scheme not in {"https", "http"}:
        raise SystemExit(f"unsupported resource URL: {url!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and _sha256(target) == expected:
        print(f"PRESENT  {target}")
        return
    if target.is_file():
        raise SystemExit(
            f"existing file does not match its manifest hash; refusing to overwrite: {target}"
        )
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.", suffix=".part", dir=target.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                while chunk := response.read(1 << 20):
                    handle.write(chunk)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            temp_path.unlink(missing_ok=True)
            raise SystemExit(f"download failed for {url}: {exc}") from exc
    actual = _sha256(temp_path)
    if actual != expected:
        temp_path.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch for {url}: {actual} != {expected}")
    os.replace(temp_path, target)
    print(f"FETCHED  {target}")


def run(manifest: Path, out_dir: Path, *, verify_only: bool) -> int:
    payload = _load_manifest(manifest)
    resources = payload["resources"]
    print(
        f"dataset={payload['dataset'].get('id')} "
        f"licences={', '.join(payload['dataset'].get('licenseSummary', []))}"
    )
    failures = 0
    for index, resource in enumerate(resources, start=1):
        if not isinstance(resource, dict):
            print(f"FAIL     resource #{index} is not an object")
            failures += 1
            continue
        target = _safe_target(out_dir, resource.get("path"))
        expected = _check_sha(resource.get("sha256"), f"resource #{index}")
        if verify_only:
            failures += not _verify_one(target, expected)
        else:
            try:
                _download(resource.get("url"), target, expected)
            except SystemExit as exc:
                print(f"FAIL     {exc}")
                failures += 1
    if failures:
        print(f"\n{failures} resource(s) failed; nothing was silently accepted")
        return 1
    print(f"\n{len(resources)} resource(s) verified")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / ".benchmark-data")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    return run(args.manifest, args.out, verify_only=args.verify_only)


if __name__ == "__main__":
    sys.exit(main())
