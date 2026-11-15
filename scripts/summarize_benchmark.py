#!/usr/bin/env python3
"""Summarize a multi-seed confirmatory validation report.

The input is a validation-report.json produced by scripts/validate_benchmark.py
with --seeds. The output is per-target and per-seed statistics; skipped runs are
never counted as successes and failed targets are retained.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from vinastudio.core.stats import bootstrap_ci, wilson_interval


def _wilson(passed: int, total: int) -> list[float] | None:
    interval = wilson_interval(passed, total)
    return [round(value, 4) for value in interval] if interval is not None else None


def summarize(report: Path, out_dir: Path) -> dict:
    payload = json.loads(report.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit("report has no cases")
    grouped: dict[str, list[dict]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        grouped.setdefault(str(case.get("id")), []).append(case)

    targets: list[dict] = []
    all_rmsd: list[float] = []
    evaluable = 0
    successes = 0
    for case_id, runs in sorted(grouped.items()):
        runs.sort(key=lambda item: int(item.get("seed", 0)))
        rmsds = [
            float(run["bestRmsd"])
            for run in runs
            if run.get("status") == "passed" and isinstance(run.get("bestRmsd"), (int, float))
        ]
        passed = sum(run.get("status") == "passed" for run in runs)
        failed = sum(run.get("status") == "failed" for run in runs)
        skipped = sum(run.get("status") == "skipped" for run in runs)
        evaluable += passed + failed
        successes += passed
        all_rmsd.extend(rmsds)
        targets.append(
            {
                "id": case_id,
                "runs": len(runs),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "successRate": round(passed / (passed + failed), 4)
                if passed + failed
                else None,
                "successRateWilson95": _wilson(passed, passed + failed),
                "meanRmsd": round(statistics.fmean(rmsds), 4) if rmsds else None,
                "medianRmsd": round(statistics.median(rmsds), 4) if rmsds else None,
                "seeds": [
                    {
                        "seed": run.get("seed"),
                        "status": run.get("status"),
                        "bestRmsd": run.get("bestRmsd"),
                        "bestAffinity": run.get("bestAffinity"),
                        "reason": run.get("reason", ""),
                    }
                    for run in runs
                ],
            }
        )

    cross_runs: dict[str, list[dict]] = {}
    kind_runs: dict[str, list[dict]] = {}
    for case in cases:
        cross = case.get("crossDocking")
        if isinstance(cross, dict):
            for row in cross.get("receptors", []):
                if not isinstance(row, dict):
                    continue
                cross_runs.setdefault(str(row.get("name") or "receptor"), []).append(row)
                kind_runs.setdefault(str(row.get("structureKind") or "holo"), []).append(row)
        elif case.get("status") in {"passed", "failed"}:
            kinds = case.get("structureKinds") or ["holo"]
            kind_runs.setdefault(str(kinds[0]), []).append(
                {"status": case.get("status"), "bestRmsd": case.get("bestRmsd")}
            )

    def _aggregate(runs: list[dict]) -> dict:
        passed = sum(1 for run in runs if run.get("status") == "passed")
        failed = sum(1 for run in runs if run.get("status") == "failed")
        rmsds = [
            float(run["bestRmsd"])
            for run in runs
            if run.get("status") == "passed"
            and isinstance(run.get("bestRmsd"), (int, float))
        ]
        return {
            "runs": len(runs),
            "passed": passed,
            "failed": failed,
            "successRate": round(passed / (passed + failed), 4)
            if passed + failed
            else None,
            "successRateWilson95": _wilson(passed, passed + failed),
            "meanRmsd": round(statistics.fmean(rmsds), 4) if rmsds else None,
        }

    summary = {
        "dataset": payload.get("dataset", {}),
        "targets": targets,
        "overall": {
            "targets": len(targets),
            "evaluableRuns": evaluable,
            "passedRuns": successes,
            "successRate": round(successes / evaluable, 4) if evaluable else None,
            "successRateWilson95": _wilson(successes, evaluable),
            "meanRmsd": round(statistics.fmean(all_rmsd), 4) if all_rmsd else None,
            "medianRmsd": round(statistics.median(all_rmsd), 4) if all_rmsd else None,
            "bootstrap95": bootstrap_ci(all_rmsd),
        },
        "crossDocking": {
            name: _aggregate(runs) for name, runs in sorted(cross_runs.items())
        },
        "byStructureKind": {
            kind: _aggregate(runs) for kind, runs in sorted(kind_runs.items())
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Confirmatory benchmark summary",
        "",
        f"Dataset: {summary['dataset'].get('id', 'unknown')}",
        f"Targets: {len(targets)}",
        f"Evaluable runs: {evaluable}",
        f"Passed runs: {successes}",
        f"Success rate: {summary['overall']['successRate']}",
        f"Success rate Wilson 95%: {summary['overall']['successRateWilson95']}",
        "",
        "| Target | Runs | Passed | Failed | Skipped | Success rate | Mean RMSD | Median RMSD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for target in targets:
        lines.append(
            f"| {target['id']} | {target['runs']} | {target['passed']} | "
            f"{target['failed']} | {target['skipped']} | {target['successRate']} | "
            f"{target['meanRmsd']} | {target['medianRmsd']} |"
        )
    if summary["crossDocking"]:
        lines += [
            "",
            "## Cross-docking receptors",
            "",
            "| Receptor | Runs | Passed | Failed | Success rate | Wilson 95% | Mean RMSD |",
            "|---|---:|---:|---:|---:|---|---:|",
        ]
        for name, stats in summary["crossDocking"].items():
            lines.append(
                f"| {name} | {stats['runs']} | {stats['passed']} | {stats['failed']} | "
                f"{stats['successRate']} | {stats['successRateWilson95']} | "
                f"{stats['meanRmsd']} |"
            )
    if summary["byStructureKind"]:
        lines += [
            "",
            "## By structure kind",
            "",
            "| Kind | Runs | Passed | Failed | Success rate | Wilson 95% | Mean RMSD |",
            "|---|---:|---:|---:|---:|---|---:|",
        ]
        for kind, stats in summary["byStructureKind"].items():
            lines.append(
                f"| {kind} | {stats['runs']} | {stats['passed']} | {stats['failed']} | "
                f"{stats['successRate']} | {stats['successRateWilson95']} | "
                f"{stats['meanRmsd']} |"
            )
    lines += [
        "",
        "Skipped runs are not counted as successes. Failed targets are retained.",
        "Wilson intervals describe this dataset; they are not a universal accuracy claim.",
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="validation-report.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = summarize(args.input, args.out)
    print(json.dumps(summary["overall"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
