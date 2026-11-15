"""``screen``: one-process headless library screening."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from vinastudio.api.screen import screen
from vinastudio.cli.config import load_screen
from vinastudio.cli.errors import InputError


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "screen", help="screen a library through one sequential worker"
    )
    parser.add_argument("--config", required=True, help="screen.json path")
    parser.add_argument(
        "--out",
        required=True,
        help="output directory or ranking .csv path",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="worker count; A2 supports 1 only",
    )
    parser.add_argument("--labels", default=None, help="override labelsPath")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    config, config_path = load_screen(args.config)
    if args.labels:
        labels = Path(args.labels).expanduser()
        if not labels.is_absolute():
            labels = Path.cwd() / labels
        config = config.model_copy(update={"labelsPath": str(labels.resolve())})

    requested = Path(args.out).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() == ".csv":
        ranking_path = requested.resolve()
        output = ranking_path.parent
    else:
        output = requested.resolve()
        ranking_path = output / "ranking.csv"
    if ranking_path.exists() and not args.overwrite:
        raise InputError(f"ranking already exists (use --overwrite): {ranking_path}")
    output.mkdir(parents=True, exist_ok=True)

    completed = screen(
        config,
        output,
        base_dir=config_path.parent,
        parallelism=args.parallelism,
    )
    if completed.ranking_path.resolve() != ranking_path:
        os.replace(completed.ranking_path, ranking_path)

    rows = completed.rows
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "screen",
        "exitCode": 0,
        "rankingPath": str(ranking_path),
        "rankingJsonPath": str(completed.ranking_json_path),
        "enrichmentPath": (
            str(completed.enrichment_path)
            if completed.enrichment_path is not None
            else None
        ),
        "counts": {
            "total": len(rows),
            "completed": sum(1 for row in rows if row["status"] == "completed"),
            "failed": sum(1 for row in rows if row["status"] != "completed"),
        },
        "rows": [
            {
                "rank": row["rank"],
                "ligandIndex": row["i"],
                "name": row["name"],
                "status": row["status"],
                "affinity": row["affinity"],
            }
            for row in rows
        ],
    }
    human = (
        f"ranking: {ranking_path}\n"
        f"{payload['counts']['completed']} completed · "
        f"{payload['counts']['failed']} failed"
    )
    if completed.enrichment_path is not None:
        human += f"\nenrichment: {completed.enrichment_path}"
    return payload, human
