"""``validate``: run a validation manifest and write JSON/Markdown reports."""

from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Any

from vinastudio.cli.errors import InputError
from vinastudio.core.stdio import engine_output_to_stderr
from vinastudio.core.validation import (
    DEFAULT_MANIFEST,
    load_manifest_document,
    missing_files,
    run_manifest,
    write_report,
)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "validate", help="run a redocking/cross-docking validation manifest"
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="validation manifest (default: validation/manifest.json)",
    )
    parser.add_argument(
        "--out",
        default="validation-output",
        help="directory for reports and case artifacts",
    )
    parser.add_argument("--case", action="append", dest="cases", metavar="ID")
    parser.add_argument("--seeds", default=None, help="comma-separated seeds")
    parser.add_argument("--exhaustiveness", type=int, default=None)
    parser.add_argument("--posebusters", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.set_defaults(handler=run)


def _seeds(value: str | None) -> list[int] | None:
    if not value:
        return None
    try:
        seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise InputError(f"--seeds must be comma-separated integers: {exc}") from exc
    if not seeds:
        raise InputError("--seeds needs at least one integer")
    return seeds


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    document = load_manifest_document(args.manifest)
    if args.list:
        cases = []
        lines = ["ID       STATUS   LICENSE                   NAME"]
        for case in document.cases:
            missing = missing_files(case)
            status = "skip" if missing else "ready"
            cases.append(
                {
                    "id": case.id,
                    "name": case.name,
                    "status": status,
                    "license": case.license or "legacy",
                    "missing": missing,
                }
            )
            lines.append(
                f"{case.id:<8} {status:<8} {(case.license or 'legacy'):<24} {case.name}"
            )
            for path in missing:
                lines.append(f"         missing: {path}")
        payload = {
            "schemaVersion": "1.0",
            "ok": True,
            "command": "validate",
            "exitCode": 0,
            "cases": cases,
        }
        return payload, "\n".join(lines)

    seed_values = _seeds(args.seeds)
    cases = document.cases
    if args.posebusters:
        cases = [replace(case, official_posebusters=True) for case in cases]
    with engine_output_to_stderr():
        report = run_manifest(
            cases,
            args.out,
            case_ids=set(args.cases) if args.cases else None,
            exhaustiveness=args.exhaustiveness,
            seeds=seed_values,
            dataset=document.dataset,
        )
    json_path, markdown_path = write_report(report, args.out)

    exit_code = 1 if report.failed else 0
    if args.strict and report.skipped:
        exit_code = 1
    rows = [
        {
            "id": result.case.id,
            "seed": result.case.seed,
            "status": result.status,
            "bestAffinity": result.best_affinity,
            "bestRmsd": result.best_rmsd,
            "reason": result.reason,
        }
        for result in report.cases
    ]
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "validate",
        "exitCode": exit_code,
        "jsonPath": str(json_path),
        "markdownPath": str(markdown_path),
        "counts": {
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
        },
        "cases": rows,
    }
    lines = [
        f"{result.case.id:<8} {result.status:<8}"
        + (
            f" affinity={result.best_affinity:7.3f}"
            if result.best_affinity is not None
            else ""
        )
        + (f" rmsd={result.best_rmsd:6.3f}" if result.best_rmsd is not None else "")
        + (f"  {result.reason}" if result.reason else "")
        for result in report.cases
    ]
    lines += [
        "",
        f"{report.passed} passed · {report.failed} failed · {report.skipped} skipped",
        f"JSON: {json_path}",
        f"Markdown: {markdown_path}",
    ]
    return payload, "\n".join(lines)
