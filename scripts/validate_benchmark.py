#!/usr/bin/env python3
"""Run the reproducible VinaStudio redocking validation manifest.

Examples:
    uv run python scripts/validate_benchmark.py --list
    uv run python scripts/validate_benchmark.py --case 1iep
    uv run python scripts/validate_benchmark.py --case 1iep --case 1hsg

The built-in 1iep case is committed. The other cases use optional local sample
files and are reported as skipped when those files are absent. This is a
redocking harness, not a leaderboard; see docs/VALIDATION.md for the limits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vinastudio.core.validation import (
    DEFAULT_MANIFEST,
    load_manifest,
    missing_files,
    run_manifest,
    write_report,
)


def _list_cases(cases) -> None:  # type: ignore[no-untyped-def]
    print(f"{'ID':<8} {'STATUS':<8} NAME")
    for case in cases:
        missing = missing_files(case)
        status = "skip" if missing else "ready"
        print(f"{case.id:<8} {status:<8} {case.name}")
        for path in missing:
            print(f"         missing: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="validation manifest (default: validation/manifest.json)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("validation-output"),
        help="directory for case artifacts and reports",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        metavar="ID",
        help="run only this case (repeatable)",
    )
    parser.add_argument(
        "--exhaustiveness",
        type=int,
        default=None,
        help="override the manifest exhaustiveness for this run",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also exit non-zero when any case is skipped",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list cases and whether their input files exist",
    )
    args = parser.parse_args(argv)

    cases = load_manifest(args.manifest)
    if args.list:
        _list_cases(cases)
        return 0

    selected = set(args.cases) if args.cases else None
    report = run_manifest(
        cases,
        args.out_dir,
        case_ids=selected,
        exhaustiveness=args.exhaustiveness,
    )
    json_path, md_path = write_report(report, args.out_dir)

    for result in report.cases:
        line = f"{result.case.id:<8} {result.status:<8}"
        if result.best_affinity is not None:
            line += f" affinity={result.best_affinity:7.3f}"
        if result.best_rmsd is not None:
            line += f" rmsd={result.best_rmsd:6.3f}"
        if result.reason:
            line += f"  {result.reason}"
        print(line)
    print(
        f"\n{report.passed} passed · {report.failed} failed · "
        f"{report.skipped} skipped"
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")

    if report.failed:
        return 1
    if args.strict and report.skipped:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
