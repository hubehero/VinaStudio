"""``dock``: run one job file and write ``result.json`` plus artifacts."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from vinastudio.api.dock import dock
from vinastudio.cli.config import load_job
from vinastudio.cli.errors import InputError


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("dock", help="run one job.json")
    parser.add_argument("--config", required=True, help="job.json path")
    parser.add_argument(
        "--out",
        required=True,
        help="result file (.json) or output directory",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    config, job_path = load_job(args.config)
    requested = Path(args.out).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() == ".json":
        result_path = requested.resolve()
        output = result_path.parent
    else:
        output = requested.resolve()
        result_path = output / "result.json"
    if result_path.exists() and not args.overwrite:
        raise InputError(f"result already exists (use --overwrite): {result_path}")
    output.mkdir(parents=True, exist_ok=True)

    completed = dock(
        config,
        output,
        base_dir=job_path.parent,
        command=" ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
    )
    if completed.result_path.resolve() != result_path.resolve():
        os.replace(completed.result_path, result_path)

    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "dock",
        "resultPath": str(result_path),
        "summary": {
            "bestAffinity": completed.result.poses[0].affinity
            if completed.result.poses
            else None,
            "nPoses": len(completed.result.poses),
            "elapsedMs": completed.elapsed_ms,
        },
        "artifacts": {
            name: str(path) for name, path in sorted(completed.artifacts.items())
        },
    }
    best = payload["summary"]["bestAffinity"]
    human = (
        f"result: {result_path}\n"
        f"poses: {payload['summary']['nPoses']} · best affinity: "
        f"{best if best is not None else '—'} kcal/mol"
    )
    return payload, human
