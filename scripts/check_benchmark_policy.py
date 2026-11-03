#!/usr/bin/env python3
"""Offline policy gate for benchmark manifests and tracked data.

This is deliberately independent of the docking stack: CI and release checks
must be able to fail on a licence/path problem without importing RDKit, Vina or
Qt. It checks the registry, every manifest, and the tracked tree.

Run:
    uv run python scripts/check_benchmark_policy.py
    uv run python scripts/check_benchmark_policy.py --root .
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = Path("validation/benchmark")
REGISTRY = BENCHMARK_DIR / "licenses.json"
MANIFESTS = BENCHMARK_DIR / "manifests"
RESTRICTED_DATA_PREFIXES = (".benchmark-data/", "validation/benchmark/data/")
RAW_SUFFIXES = (".pdb", ".pdbqt", ".sdf", ".mol2", ".cif")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [value for value in result.stdout.split("\0") if value]


def _registry(root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(root / REGISTRY)
    if not isinstance(payload, dict) or not isinstance(payload.get("licenses"), dict):
        raise ValueError("licenses.json must contain a licenses object")
    registry = payload["licenses"]
    if not isinstance(registry, dict) or not registry:
        raise ValueError("licenses.json has no entries")
    for license_id, entry in registry.items():
        if not isinstance(entry, dict):
            raise ValueError(f"licence {license_id!r} is not an object")
        if not isinstance(entry.get("redistributable"), bool):
            raise ValueError(f"licence {license_id!r} needs a boolean redistributable")
        if entry.get("tier") not in {"open", "attribution", "local-restricted", "unconfirmed"}:
            raise ValueError(f"licence {license_id!r} has an unknown tier")
        if entry.get("tier") == "unconfirmed" and entry["redistributable"]:
            raise ValueError(f"unconfirmed licence {license_id!r} cannot be redistributable")
    return registry


def _manifest_errors(path: Path, registry: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    try:
        payload = _load_json(path)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(payload, dict):
        return [f"{path}: manifest must be an object"]
    version = payload.get("formatVersion")
    if version != "1.1":
        errors.append(f"{path}: benchmark manifest must use formatVersion 1.1")
        return errors
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        return [f"{path}: missing dataset object"]
    dataset_id = str(dataset.get("id", "")).strip()
    if not dataset_id:
        errors.append(f"{path}: dataset needs an id")
    summary = dataset.get("licenseSummary")
    if not isinstance(summary, list) or not summary:
        errors.append(f"{path}: dataset needs a licenseSummary")
        summary = []
    dataset_redistributable = dataset.get("redistributable")
    if not isinstance(dataset_redistributable, bool):
        errors.append(f"{path}: dataset redistributable must be boolean")
        dataset_redistributable = False
    for license_id in summary:
        if license_id not in registry:
            errors.append(f"{path}: unknown dataset licence {license_id!r}")
        elif registry[license_id].get("tier") == "unconfirmed":
            errors.append(f"{path}: unconfirmed dataset licence {license_id!r}")
        elif dataset_redistributable and not registry[license_id]["redistributable"]:
            errors.append(f"{path}: dataset claims redistribution with {license_id!r}")

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(f"{path}: missing cases")
        return errors
    seen: set[str] = set()
    for index, case in enumerate(cases, start=1):
        label = f"{path}: case #{index}"
        if not isinstance(case, dict):
            errors.append(f"{label} is not an object")
            continue
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            errors.append(f"{label} has no id")
        elif case_id in seen:
            errors.append(f"{path}: duplicate case id {case_id!r}")
        seen.add(case_id)
        license_id = case.get("license")
        if not isinstance(license_id, str) or license_id not in registry:
            errors.append(f"{label} has unknown licence {license_id!r}")
            continue
        if license_id not in summary:
            errors.append(f"{label} licence {license_id!r} is absent from dataset licenseSummary")
        redistributable = case.get("redistributable")
        if not isinstance(redistributable, bool):
            errors.append(f"{label} redistributable must be boolean")
            continue
        if redistributable and not registry[license_id]["redistributable"]:
            errors.append(f"{label} claims redistribution for restricted licence {license_id!r}")
        if redistributable and dataset_redistributable is False:
            errors.append(f"{label} is redistributable in a restricted dataset")
        if not redistributable and dataset_redistributable is True:
            errors.append(f"{label} is restricted in a redistributable dataset")
        if case.get("localOnly") is True and redistributable:
            errors.append(f"{label} is both localOnly and redistributable")
        source = case.get("source")
        if not isinstance(source, str) or not source.strip():
            errors.append(f"{label} needs source")
        source_url = case.get("sourceUrl")
        if not isinstance(source_url, str) or not source_url.strip():
            errors.append(f"{label} needs sourceUrl")
        accessed = case.get("accessedAt")
        if not isinstance(accessed, str) or len(accessed) != 10:
            errors.append(f"{label} needs accessedAt YYYY-MM-DD")
        digest = case.get("sourceSha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            ch not in "0123456789abcdefABCDEF" for ch in digest
        ):
            errors.append(f"{label} needs a 64-character sourceSha256")

    resources = payload.get("resources", [])
    if not isinstance(resources, list):
        errors.append(f"{path}: resources must be a list")
        resources = []
    for index, resource in enumerate(resources, start=1):
        label = f"{path}: resource #{index}"
        if not isinstance(resource, dict):
            errors.append(f"{label} is not an object")
            continue
        relative = resource.get("path")
        if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
            errors.append(f"{label} needs a relative path")
        elif ".." in Path(relative).parts:
            errors.append(f"{label} path must not contain '..'")
        url = resource.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            errors.append(f"{label} needs an http(s) URL")
        digest = resource.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"{label} needs a 64-character sha256")
    return errors


def _tracked_errors(root: Path, tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for path in tracked:
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in RESTRICTED_DATA_PREFIXES):
            errors.append(f"restricted benchmark data is tracked: {path}")
            continue
        if (
            path.startswith(f"{BENCHMARK_DIR.as_posix()}/")
            and not path.endswith((".md", ".json", ".gitkeep"))
            and (fnmatch.fnmatch(path, "*.pdb*") or path.endswith(RAW_SUFFIXES))
        ):
            errors.append(f"raw benchmark data is tracked: {path}")
    return errors


def check(root: Path = REPO_ROOT, *, tracked: list[str] | None = None) -> list[str]:
    registry = _registry(root)
    errors: list[str] = []
    manifests = sorted((root / MANIFESTS).glob("*.json"))
    for path in manifests:
        if path.name.endswith(("-audit.json", "-selection.json")):
            continue
        errors.extend(_manifest_errors(path, registry))
    files = _tracked_files(root) if tracked is None else tracked
    errors.extend(_tracked_errors(root, files))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        errors = check(args.root.resolve())
    except (OSError, ValueError) as exc:
        print(f"FAIL  {exc}")
        return 1
    if errors:
        for error in errors:
            print(f"FAIL  {error}")
        return 1
    print("PASS  benchmark licences, manifests and tracked paths are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
