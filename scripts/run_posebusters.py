#!/usr/bin/env python3
"""Run official PoseBusters on an existing validation report.

The project's six geometry checks and official PoseBusters are separate
instruments. This script reads the already-generated ``poses.pdbqt`` artifacts,
converts them through the same exporter the application uses, and runs
PoseBusters' ``redock`` configuration. It never re-runs docking and never
replaces the project's RMSD/geometry result.

Optional dependency (pinned for the recorded run):
    uv run --with posebusters==0.6.5 python scripts/run_posebusters.py \
      --report validation-output/benchmark-confirmatory/validation-report.json \
      --out validation-output/benchmark-confirmatory/posebusters.json
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

from vinastudio.core.chem.export import poses_to_sdf

REPO_ROOT = Path(__file__).resolve().parent.parent


def _case_dir(report_path: Path, case: dict) -> Path:
    root = report_path.parent / "cases"
    case_id = str(case.get("id"))
    seed = case.get("seed")
    if seed is not None:
        candidate = root / f"{case_id}-seed{seed}"
        if candidate.is_dir():
            return candidate
    return root / case_id


def _condition_pdb(case_dir: Path, case: dict) -> Path:
    """Protein-only condition matching the receptor preparation.

    Waters and non-kept HETATM are removed; the native ligand is removed;
    retained site cofactors are kept. This is the conditioning molecule used
    for docking, so water tests are not falsely applied to deleted waters.
    """
    inputs = case.get("provenance", {}).get("inputs", {})
    source = Path(inputs["receptor"]["path"])
    ligand = Path(inputs.get("ligand", {}).get("path", "")).stem
    params = case.get("provenance", {}).get("parameters", {})
    keep = set(params.get("keepHetero", []))
    target = case_dir / "posebusters_condition.pdb"
    if target.is_file():
        return target
    lines = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM", "TER", "END")):
            continue
        if line.startswith("HETATM"):
            residue = line[17:20].strip()
            key = f"{line[21:22].strip()}:{line[22:26].strip()}"
            if residue == ligand or residue == "HOH" or key not in keep:
                continue
        lines.append(line)
    lines.append("END")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _write_not_run(report: dict, out: Path, reason: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "status": "not-run",
                "reason": reason,
                "dataset": report.get("dataset", {}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run(report_path: Path, out: Path) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        from posebusters import PoseBusters
    except ImportError as exc:
        _write_not_run(report, out, f"official PoseBusters is not installed: {exc}")
        print("PoseBusters not installed; wrote not-run record", file=sys.stderr)
        return 0

    version = importlib.metadata.version("posebusters")
    buster = PoseBusters(config="redock")
    cases: list[dict] = []
    errors: list[str] = []
    top_passed = 0
    all_passed = 0
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id"))
        seed = case.get("seed")
        case_dir = _case_dir(report_path, case)
        pdbqt = case_dir / "docking" / "poses.pdbqt"
        if not pdbqt.is_file():
            errors.append(f"{case_id}/seed{seed}: missing {pdbqt}")
            continue
        inputs = case.get("provenance", {}).get("inputs", {})
        try:
            pred = case_dir / "poses.sdf"
            if not pred.is_file():
                pred.write_text(poses_to_sdf(pdbqt.read_text()).sdf, encoding="utf-8")
            true = Path(inputs["reference"]["path"])
            cond = _condition_pdb(case_dir, case)
            if not true.is_file() or not cond.is_file():
                raise FileNotFoundError(f"missing reference or receptor for {case_id}")
            frame = buster.bust(pred, true, cond, full_report=False)
            bools = frame.select_dtypes(include=["bool"]).fillna(False)
            rows = []
            for pose_index, (_index, row) in enumerate(bools.iterrows()):
                failed = [str(column) for column, value in row.items() if not bool(value)]
                rows.append(
                    {
                        "pose": pose_index,
                        "passed": not failed,
                        "failedChecks": failed,
                    }
                )
            top = rows[0] if rows else None
            case_all = all(row["passed"] for row in rows)
            cases.append(
                {
                    "id": case_id,
                    "seed": seed,
                    "poseCount": len(rows),
                    "topPassed": bool(top and top["passed"]),
                    "allPosesPassed": case_all,
                    "topFailedChecks": top["failedChecks"] if top else ["no PoseBusters rows"],
                    "poses": rows,
                }
            )
            top_passed += int(bool(top and top["passed"]))
            all_passed += int(case_all)
        except Exception as exc:  # noqa: BLE001 - report one case, continue the set
            errors.append(f"{case_id}/seed{seed}: {type(exc).__name__}: {exc}")

    payload = {
        "status": "run" if not errors else "partial",
        "posebustersVersion": version,
        "config": "redock",
        "dataset": report.get("dataset", {}),
        "summary": {
            "cases": len(cases),
            "attempted": len(report.get("cases", [])),
            "topPosePassed": top_passed,
            "allPosesPassed": all_passed,
            "errors": len(errors),
        },
        "cases": cases,
        "errors": errors,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
