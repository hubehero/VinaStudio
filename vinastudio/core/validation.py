"""Reproducible redocking validation for VinaStudio.

This is deliberately a *harness*, not a leaderboard. It runs the same
prepare → box → dock → RMSD → geometry checks path the application uses, one
manifest case at a time, and writes a report that includes the versions, box,
warnings and per-pose findings. A case passes only when the best pose is within
the configured RMSD threshold and the geometry checks report no error.

The six geometry checks are the project's PoseBusters-style subset; they are not
the official PoseBusters suite and a pass here is not a claim of universal
accuracy. Missing files become ``skipped`` so a fresh checkout/CI can run the
committed 1iep case without failing on optional local datasets.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from vinastudio.core.box import Box, autobox, points_from_rdkit_file
from vinastudio.core.chem.ligand_prep import prepare_ligand
from vinastudio.core.chem.pdbqt import parse_pdbqt
from vinastudio.core.chem.pose_validation import validate_poses, worst_severity
from vinastudio.core.chem.receptor_prep import ReceptorPrepOptions, prepare_receptor
from vinastudio.core.chem.rmsd import rmsd_vs_reference
from vinastudio.core.docking import DockingParams, run_docking
from vinastudio.core.errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "validation" / "manifest.json"
DEFAULT_RMSD_THRESHOLD = 2.0

ValidationStatus = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True, slots=True)
class ValidationCase:
    """One redocking case; paths are absolute by the time it is run."""

    id: str
    name: str
    receptor: Path
    ligand: Path
    reference: Path
    center: tuple[float, float, float] | None = None
    size: tuple[float, float, float] | None = None
    extend: float = 4.0
    exhaustiveness: int = 8
    n_poses: int = 9
    seed: int = 42
    scoring: str = "vina"
    rmsd_threshold: float = DEFAULT_RMSD_THRESHOLD
    affinity_range: tuple[float, float] | None = None
    allow_bad_residues: bool = False


@dataclass(slots=True)
class ValidationCaseResult:
    case: ValidationCase
    status: ValidationStatus
    reason: str = ""
    best_affinity: float | None = None
    best_rmsd: float | None = None
    pose_count: int = 0
    receptor_atoms: int | None = None
    ligand_atoms: int | None = None
    box: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    worst_check: str | None = None
    error_poses: int = 0
    warning_poses: int = 0
    receptor_warnings: list[str] = field(default_factory=list)
    ligand_warnings: list[str] = field(default_factory=list)
    elapsed_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "name": self.case.name,
            "status": self.status,
            "reason": self.reason,
            "bestAffinity": self.best_affinity,
            "bestRmsd": self.best_rmsd,
            "poseCount": self.pose_count,
            "receptorAtoms": self.receptor_atoms,
            "ligandAtoms": self.ligand_atoms,
            "box": self.box,
            "checks": self.checks,
            "worstCheck": self.worst_check,
            "errorPoses": self.error_poses,
            "warningPoses": self.warning_poses,
            "receptorWarnings": self.receptor_warnings,
            "ligandWarnings": self.ligand_warnings,
            "elapsedMs": self.elapsed_ms,
        }


@dataclass(slots=True)
class ValidationReport:
    cases: list[ValidationCaseResult]
    generated_at: str
    environment: dict[str, str]

    @property
    def passed(self) -> int:
        return sum(1 for result in self.cases if result.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for result in self.cases if result.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for result in self.cases if result.status == "skipped")

    def as_dict(self) -> dict[str, Any]:
        return {
            "formatVersion": "1.0",
            "generatedAt": self.generated_at,
            "environment": self.environment,
            "summary": {
                "total": len(self.cases),
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "cases": [result.as_dict() for result in self.cases],
        }


def environment_info() -> dict[str, str]:
    """Versions that can change a docking result; unknown is reported as such."""
    versions: dict[str, str] = {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }
    for distribution in ("vina", "meeko", "rdkit", "numpy"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "unknown"
    return versions


def load_manifest(
    path: str | Path = DEFAULT_MANIFEST,
    *,
    root: str | Path = REPO_ROOT,
) -> list[ValidationCase]:
    """Parse a validation manifest; paths are relative to *root* by default."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise InvalidInputError(f"validation manifest not found: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"validation manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidInputError("validation manifest must be a JSON object")
    if str(payload.get("formatVersion", "")) != "1.0":
        raise InvalidInputError("validation manifest formatVersion must be '1.0'")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise InvalidInputError("validation manifest must contain a non-empty cases list")

    base = Path(root)
    cases: list[ValidationCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise InvalidInputError(f"validation case #{index} must be an object")
        case_id = str(raw.get("id", "")).strip()
        if not case_id:
            raise InvalidInputError(f"validation case #{index} has no id")
        if case_id in seen:
            raise InvalidInputError(f"duplicate validation case id: {case_id}")
        seen.add(case_id)
        cases.append(_case_from_dict(raw, base, case_id))
    return cases


def _case_from_dict(
    raw: dict[str, Any],
    base: Path,
    case_id: str,
) -> ValidationCase:
    def path_value(key: str) -> Path:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InvalidInputError(f"validation case {case_id!r} needs {key}")
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

    center = _triple(raw.get("center"), "center", case_id)
    size = _triple(raw.get("size"), "size", case_id)
    if (center is None) != (size is None):
        raise InvalidInputError(
            f"validation case {case_id!r} needs both center and size, or neither"
        )
    affinity = _pair(raw.get("affinityRange"), "affinityRange", case_id)
    if affinity is not None and affinity[0] > affinity[1]:
        raise InvalidInputError(
            f"validation case {case_id!r} affinityRange low must not exceed high"
        )
    return ValidationCase(
        id=case_id,
        name=str(raw.get("name") or case_id),
        receptor=path_value("receptor"),
        ligand=path_value("ligand"),
        reference=path_value("reference"),
        center=center,
        size=size,
        extend=_number(raw.get("extend", 4.0), "extend", case_id),
        exhaustiveness=int(_number(raw.get("exhaustiveness", 8), "exhaustiveness", case_id)),
        n_poses=int(_number(raw.get("nPoses", 9), "nPoses", case_id)),
        seed=int(_number(raw.get("seed", 42), "seed", case_id)),
        scoring=str(raw.get("scoring", "vina")),
        rmsd_threshold=_number(
            raw.get("rmsdThreshold", DEFAULT_RMSD_THRESHOLD), "rmsdThreshold", case_id
        ),
        affinity_range=affinity,
        allow_bad_residues=bool(raw.get("allowBadResidues", False)),
    )


def _number(value: Any, key: str, case_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"validation case {case_id!r} {key} must be a number")
    return float(value)


def _triple(value: Any, key: str, case_id: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 3:
        raise InvalidInputError(f"validation case {case_id!r} {key} must be 3 numbers")
    numbers = tuple(_number(item, key, case_id) for item in value)
    return (numbers[0], numbers[1], numbers[2])


def _pair(value: Any, key: str, case_id: str) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise InvalidInputError(f"validation case {case_id!r} {key} must be 2 numbers")
    low, high = (_number(item, key, case_id) for item in value)
    return (low, high)


def missing_files(case: ValidationCase) -> list[str]:
    return [
        str(path)
        for path in (case.receptor, case.ligand, case.reference)
        if not path.is_file()
    ]


def box_for_case(case: ValidationCase) -> Box:
    """Explicit box or a box derived from the reference ligand's heavy atoms."""
    if case.center is not None and case.size is not None:
        return Box(center=case.center, size=case.size)
    points = points_from_rdkit_file(case.reference)
    return autobox(points, extend=case.extend)


def failure_reasons(
    case: ValidationCase,
    *,
    pose_count: int,
    best_rmsd: float | None,
    best_affinity: float | None,
    best_pose_error: bool,
    error_poses: int = 0,
) -> list[str]:
    """The single place that decides whether a completed case passes."""
    reasons: list[str] = []
    if pose_count <= 0:
        reasons.append("docking produced no poses")
        return reasons
    if best_rmsd is None:
        reasons.append("RMSD could not be computed")
    elif best_rmsd > case.rmsd_threshold:
        reasons.append(
            f"best RMSD {best_rmsd:.3f} Å exceeds {case.rmsd_threshold:.3f} Å"
        )
    if best_pose_error:
        reasons.append("the best pose has a geometry error")
    if case.affinity_range is not None and best_affinity is not None:
        low, high = case.affinity_range
        if not low <= best_affinity <= high:
            reasons.append(
                f"best affinity {best_affinity:.3f} is outside [{low:.3f}, {high:.3f}]"
            )
    return reasons


def run_case(
    case: ValidationCase,
    out_dir: str | Path,
    *,
    exhaustiveness: int | None = None,
) -> ValidationCaseResult:
    """Run one case; never raises for a case-level failure."""
    missing = missing_files(case)
    if missing:
        return ValidationCaseResult(
            case=case,
            status="skipped",
            reason="missing input: " + ", ".join(missing),
        )

    if exhaustiveness is not None:
        case = replace(case, exhaustiveness=exhaustiveness)
    case_dir = Path(out_dir) / "cases" / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        ligand = prepare_ligand(case.ligand)
        receptor = prepare_receptor(
            case.receptor,
            ReceptorPrepOptions(allow_bad_residues=case.allow_bad_residues),
        )
        ligand_path = case_dir / "ligand.pdbqt"
        receptor_path = case_dir / "receptor.pdbqt"
        ligand_path.write_text(ligand.pdbqt, encoding="utf-8")
        receptor_path.write_text(receptor.pdbqt, encoding="utf-8")

        box = box_for_case(case)
        params = DockingParams(
            receptor_path=str(receptor_path),
            ligand_path=str(ligand_path),
            center=box.center,
            size=box.size,
            exhaustiveness=case.exhaustiveness,
            n_poses=case.n_poses,
            seed=case.seed,
            scoring=case.scoring,
        )
        result = run_docking(params, str(case_dir / "docking"))
        receptor_atoms = parse_pdbqt(receptor.pdbqt).first_pose.n_atoms
        ligand_atoms = parse_pdbqt(ligand.pdbqt).first_pose.n_atoms

        if not result.poses or not result.poses_sdf.strip():
            return ValidationCaseResult(
                case=case,
                status="failed",
                reason="docking produced no poses",
                receptor_atoms=receptor_atoms,
                ligand_atoms=ligand_atoms,
                box=box.summary(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                receptor_warnings=list(receptor.report.warnings),
                ligand_warnings=list(ligand.report.warnings),
            )

        rmsds = rmsd_vs_reference(result.poses_sdf, case.reference)
        findings = validate_poses(result.poses_sdf, reference=case.reference, box=box)
        best_findings = findings[0]
        error_poses = sum(1 for pose in findings if worst_severity(pose) == "error")
        warning_poses = sum(1 for pose in findings if worst_severity(pose) == "warning")
        best_rmsd = rmsds[0] if rmsds else None
        reasons = failure_reasons(
            case,
            pose_count=len(result.poses),
            best_rmsd=best_rmsd,
            best_affinity=result.best_affinity,
            best_pose_error=worst_severity(best_findings) == "error",
            error_poses=error_poses,
        )
        return ValidationCaseResult(
            case=case,
            status="failed" if reasons else "passed",
            reason="; ".join(reasons),
            best_affinity=result.best_affinity,
            best_rmsd=best_rmsd,
            pose_count=len(result.poses),
            receptor_atoms=receptor_atoms,
            ligand_atoms=ligand_atoms,
            box=box.summary(),
            checks=[finding.as_dict() for finding in best_findings],
            worst_check=worst_severity(best_findings),
            error_poses=error_poses,
            warning_poses=warning_poses,
            receptor_warnings=list(receptor.report.warnings),
            ligand_warnings=list(ligand.report.warnings),
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - a case failure must not stop the run
        return ValidationCaseResult(
            case=case,
            status="failed",
            reason=f"{type(exc).__name__}: {exc}",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


def run_manifest(
    cases: list[ValidationCase],
    out_dir: str | Path,
    *,
    case_ids: set[str] | None = None,
    exhaustiveness: int | None = None,
) -> ValidationReport:
    selected = [case for case in cases if case_ids is None or case.id in case_ids]
    if case_ids is not None:
        unknown = case_ids - {case.id for case in selected}
        if unknown:
            raise InvalidInputError(f"unknown validation case(s): {sorted(unknown)}")
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    results = [
        run_case(case, output, exhaustiveness=exhaustiveness) for case in selected
    ]
    return ValidationReport(
        cases=results,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        environment=environment_info(),
    )


def write_report(report: ValidationReport, out_dir: str | Path) -> tuple[Path, Path]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "validation-report.json"
    md_path = output / "validation-report.md"
    json_path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_markdown(report), encoding="utf-8")
    return json_path, md_path


def format_markdown(report: ValidationReport) -> str:
    lines = [
        "# VinaStudio validation report",
        "",
        f"Generated: {report.generated_at}",
        "",
        "This is a reproducible redocking check, not an accuracy ranking. "
        "The geometry checks are a PoseBusters-style subset, not the official suite.",
        "",
        "## Environment",
        "",
        "| Item | Value |",
        "|---|---|",
    ]
    for key, value in report.environment.items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        f"**Summary:** {report.passed} passed · {report.failed} failed · "
        f"{report.skipped} skipped",
        "",
        "## Cases",
        "",
        "| Case | Status | Best affinity | RMSD | Poses | Error poses | Reason |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for result in report.cases:
        affinity = "—" if result.best_affinity is None else f"{result.best_affinity:.3f}"
        rmsd = "—" if result.best_rmsd is None else f"{result.best_rmsd:.3f}"
        reason = result.reason.replace("|", "\\|")
        lines.append(
            f"| {result.case.id} | {result.status} | {affinity} | {rmsd} | "
            f"{result.pose_count} | {result.error_poses} | {reason} |"
        )
    lines += [
        "",
        "A pass means: at least one pose, best RMSD within the configured threshold, "
        "no geometry error in the best pose, and any configured affinity range met. "
        "Warnings are recorded but do not fail a case. Skipped cases mean their "
        "optional input files are absent; they are not evidence of success.",
        "",
    ]
    return "\n".join(lines)
