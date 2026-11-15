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

import json
import re
import statistics as statistics_module
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
from vinastudio.core.chem.rmsd import reference_matches_poses, rmsd_vs_reference
from vinastudio.core.docking import DockingParams, run_docking
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.stats import bootstrap_ci, wilson_interval

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "validation" / "manifest.json"
DEFAULT_RMSD_THRESHOLD = 2.0

LEGACY_MANIFEST_VERSION = "1.0"
BENCHMARK_MANIFEST_VERSION = "1.1"
CROSS_DOCKING_MANIFEST_VERSION = "1.2"
REPORT_SCHEMA_VERSION = "2.2"
#: A cross-docking receptor must be in the reference frame; the closest
#: reference-ligand/receptor atom pair is a cheap sanity check, not proof that
#: the pocket is correct.
FRAME_MAX_MIN_DISTANCE = 5.0
OPEN_LICENSES = frozenset({"CC0-1.0", "MIT", "CC-BY-3.0", "CC-BY-SA-3.0"})
RESTRICTED_LICENSES = frozenset(
    {"PDBbind-User-Agreement", "DUD-E-Terms", "ZINC-Terms", "Unconfirmed"}
)
KNOWN_LICENSES = OPEN_LICENSES | RESTRICTED_LICENSES
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ValidationStatus = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True, slots=True)
class ValidationDataset:
    """Dataset-level licence and redistribution metadata."""

    id: str
    name: str = ""
    license_summary: tuple[str, ...] = ()
    redistributable: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "licenseSummary": list(self.license_summary),
            "redistributable": self.redistributable,
        }


@dataclass(frozen=True, slots=True)
class ValidationManifest:
    """Parsed manifest with its dataset record; ``cases`` stays list-compatible."""

    cases: list[ValidationCase]
    dataset: ValidationDataset | None = None



@dataclass(frozen=True, slots=True)
class ValidationCase:
    """One redocking case; paths are absolute by the time it is run."""

    id: str
    name: str
    receptor: Path
    ligand: Path
    reference: Path
    mode: str = "self"
    """``self`` (one receptor) or ``cross`` (several pre-aligned receptors)."""
    receptors: tuple[Path, ...] = ()
    receptor_names: tuple[str, ...] = ()
    structure_kinds: tuple[str, ...] = ()
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
    default_altloc: str = ""
    keep_hetero: tuple[str, ...] = ()
    box_source: str = ""
    official_posebusters: bool = False
    reference_source: str = ""
    dataset: str = "legacy"
    source: str = ""
    license: str = ""
    redistributable: bool | None = None
    local_only: bool = False
    source_url: str = ""
    accessed_at: str = ""
    source_sha256: str = ""
    target_family: str = ""
    ligand_chain: str = ""
    ligand_residue: str = ""


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
    provenance: dict[str, Any] = field(default_factory=dict)
    official_posebusters: dict[str, Any] | None = None
    cross_docking: dict[str, Any] | None = None
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
            "provenance": self.provenance,
            "officialPoseBusters": self.official_posebusters,
            "crossDocking": self.cross_docking,
            "elapsedMs": self.elapsed_ms,
            "seed": self.case.seed,
            "source": self.case.source,
            "license": self.case.license,
            "redistributable": self.case.redistributable,
            "localOnly": self.case.local_only,
            "targetFamily": self.case.target_family,
            "mode": self.case.mode,
            "structureKinds": list(self.case.structure_kinds),
        }


def _report_statistics(cases: list[ValidationCaseResult]) -> dict[str, Any]:
    """Descriptive statistics for this dataset, not a universal accuracy claim."""
    evaluable = [result for result in cases if result.status in {"passed", "failed"}]
    rmsds = [
        result.best_rmsd
        for result in evaluable
        if result.best_rmsd is not None
    ]
    passed = sum(1 for result in evaluable if result.status == "passed")
    success_rate = passed / len(evaluable) if evaluable else None
    wilson = wilson_interval(passed, len(evaluable)) if evaluable else None
    bootstrap = bootstrap_ci(rmsds)
    return {
        "n": len(evaluable),
        "passed": passed,
        "successRate": round(success_rate, 4) if success_rate is not None else None,
        "successRateWilson95": (
            [round(value, 4) for value in wilson] if wilson is not None else None
        ),
        "meanRmsd": (
            round(statistics_module.fmean(rmsds), 4) if rmsds else None
        ),
        "medianRmsd": (
            round(statistics_module.median(rmsds), 4) if rmsds else None
        ),
        "bootstrap95": (
            [round(value, 4) for value in bootstrap] if bootstrap is not None else None
        ),
    }


@dataclass(slots=True)
class ValidationReport:
    cases: list[ValidationCaseResult]
    generated_at: str
    environment: dict[str, str]
    dataset: ValidationDataset | None = None

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
        dataset = self.dataset or ValidationDataset(
            id="legacy",
            name="Legacy 1IEP control",
            license_summary=(),
            redistributable=None,
        )
        summary: dict[str, Any] = {
            "total": len(self.cases),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
        }
        official = [
            result.official_posebusters
            for result in self.cases
            if result.official_posebusters
            and result.official_posebusters.get("status") == "run"
        ]
        if official:
            summary["officialCases"] = len(official)
            summary["officialTopPassed"] = sum(
                1 for item in official if item.get("summary", {}).get("topPassed")
            )
            summary["officialAllPosesPassed"] = sum(
                1 for item in official if item.get("summary", {}).get("allPosesPassed")
            )
        return {
            "formatVersion": REPORT_SCHEMA_VERSION,
            "generatedAt": self.generated_at,
            "environment": self.environment,
            "dataset": dataset.as_dict(),
            "summary": summary,
            "statistics": _report_statistics(self.cases),
            "cases": [result.as_dict() for result in self.cases],
        }


def _git_metadata() -> dict[str, str | bool | None]:
    from vinastudio.core.provenance import git_metadata

    return git_metadata(REPO_ROOT)


def _display_path(path: Path, *, redact: bool) -> str:
    from vinastudio.core.provenance import display_path

    return display_path(path, redact=redact, relative_to_root=True)


def _file_info(path: Path, *, redact: bool = False) -> dict[str, Any]:
    from vinastudio.core.provenance import file_info

    return file_info(path, redact=redact, relative_to_root=True)


def _docking_provenance(case: ValidationCase, params: DockingParams, box: Box) -> dict[str, Any]:
    return {
        "engine": params.engine,
        "scoring": params.scoring,
        "weights": params.weights,
        "exhaustiveness": params.exhaustiveness,
        "nPoses": params.n_poses,
        "seed": params.seed,
        "energyRange": params.energy_range,
        "minRmsd": params.min_rmsd,
        "maxEvals": params.max_evals,
        "cpu": params.cpu,
        "noRefine": params.no_refine,
        "spacing": params.spacing,
        "forceEvenVoxels": params.force_even_voxels,
        "boxSource": case.box_source
        or ("explicit" if case.center is not None else "reference-autobox"),
        "box": box.summary(),
        "allowBadResidues": case.allow_bad_residues,
        "defaultAltloc": case.default_altloc,
        "keepHetero": list(case.keep_hetero),
    }


def environment_info() -> dict[str, str]:
    from vinastudio.core.provenance import environment_info as _environment_info

    return _environment_info()


def _required_text(raw: dict[str, Any], key: str, case_id: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"validation case {case_id!r} needs {key}")
    return value.strip()


def _required_bool(raw: dict[str, Any], key: str, case_id: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise InvalidInputError(f"validation case {case_id!r} {key} must be a boolean")
    return value


def _validate_license(case_id: str, license_id: str, redistributable: bool, local_only: bool) -> None:
    if license_id not in KNOWN_LICENSES:
        raise InvalidInputError(
            f"validation case {case_id!r} has unknown license {license_id!r}; "
            "add it to validation/benchmark/licenses.json"
        )
    if redistributable and license_id not in OPEN_LICENSES:
        raise InvalidInputError(
            f"validation case {case_id!r} marks {license_id!r} redistributable, "
            "but that licence is not open"
        )
    if local_only and redistributable:
        raise InvalidInputError(
            f"validation case {case_id!r} cannot be both localOnly and redistributable"
        )


def _dataset_from_dict(raw: Any) -> ValidationDataset:
    if not isinstance(raw, dict):
        raise InvalidInputError("benchmark manifest needs a dataset object")
    dataset_id = str(raw.get("id", "")).strip()
    if not dataset_id:
        raise InvalidInputError("benchmark dataset needs an id")
    summary = raw.get("licenseSummary")
    if not isinstance(summary, list) or not summary:
        raise InvalidInputError("benchmark dataset needs a non-empty licenseSummary list")
    licenses: list[str] = []
    for value in summary:
        if not isinstance(value, str) or value not in KNOWN_LICENSES:
            raise InvalidInputError(
                f"benchmark dataset has unknown license {value!r}; "
                "add it to validation/benchmark/licenses.json"
            )
        licenses.append(value)
    redistributable = raw.get("redistributable")
    if not isinstance(redistributable, bool):
        raise InvalidInputError("benchmark dataset redistributable must be a boolean")
    if redistributable and any(value not in OPEN_LICENSES for value in licenses):
        raise InvalidInputError(
            "benchmark dataset claims redistribution but includes a non-open licence"
        )
    return ValidationDataset(
        id=dataset_id,
        name=str(raw.get("name") or dataset_id),
        license_summary=tuple(licenses),
        redistributable=redistributable,
    )


def load_manifest_document(
    path: str | Path = DEFAULT_MANIFEST,
    *,
    root: str | Path = REPO_ROOT,
) -> ValidationManifest:
    """Parse a 1.0, 1.1 or 1.2 manifest, including dataset-level metadata."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise InvalidInputError(f"validation manifest not found: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"validation manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidInputError("validation manifest must be a JSON object")
    version = str(payload.get("formatVersion", ""))
    if version not in {
        LEGACY_MANIFEST_VERSION,
        BENCHMARK_MANIFEST_VERSION,
        CROSS_DOCKING_MANIFEST_VERSION,
    }:
        raise InvalidInputError(
            "validation manifest formatVersion must be '1.0', '1.1' or '1.2'"
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise InvalidInputError("validation manifest must contain a non-empty cases list")
    dataset = (
        _dataset_from_dict(payload.get("dataset"))
        if version != LEGACY_MANIFEST_VERSION
        else None
    )

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
        cases.append(_case_from_dict(raw, base, case_id, version, dataset))

    if dataset is not None:
        for case in cases:
            if case.license not in dataset.license_summary:
                raise InvalidInputError(
                    f"validation case {case.id!r} licence {case.license!r} "
                    "is not in the dataset licenseSummary"
                )
            if dataset.redistributable and not case.redistributable:
                raise InvalidInputError(
                    f"validation case {case.id!r} is restricted in a redistributable dataset"
                )
            if dataset.redistributable is False and case.redistributable:
                raise InvalidInputError(
                    f"validation case {case.id!r} is redistributable in a restricted dataset"
                )
    return ValidationManifest(cases=cases, dataset=dataset)


def load_manifest(
    path: str | Path = DEFAULT_MANIFEST,
    *,
    root: str | Path = REPO_ROOT,
) -> list[ValidationCase]:
    """Compatibility wrapper; use :func:`load_manifest_document` for metadata."""
    return load_manifest_document(path, root=root).cases


def _receptors_from_dict(
    raw: dict[str, Any],
    base: Path,
    case_id: str,
) -> tuple[tuple[Path, ...], tuple[str, ...], tuple[str, ...]]:
    entries = raw.get("receptors")
    if entries is None:
        return (), (), ()
    if not isinstance(entries, list) or len(entries) < 2:
        raise InvalidInputError(
            f"validation case {case_id!r} receptors must list at least two receptors"
        )
    paths: list[Path] = []
    names: list[str] = []
    kinds: list[str] = []
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            raise InvalidInputError(
                f"validation case {case_id!r} receptor #{index} must be an object"
            )
        value = item.get("path")
        if not isinstance(value, str) or not value.strip():
            raise InvalidInputError(
                f"validation case {case_id!r} receptor #{index} needs path"
            )
        candidate = Path(value)
        paths.append(candidate if candidate.is_absolute() else (base / candidate).resolve())
        names.append(str(item.get("name") or f"receptor-{index}"))
        kind = str(item.get("structureKind", "holo"))
        if kind not in {"holo", "apo", "predicted"}:
            raise InvalidInputError(
                f"validation case {case_id!r} receptor #{index} has unknown "
                f"structureKind {kind!r}"
            )
        kinds.append(kind)
    return tuple(paths), tuple(names), tuple(kinds)


def _case_from_dict(
    raw: dict[str, Any],
    base: Path,
    case_id: str,
    version: str = LEGACY_MANIFEST_VERSION,
    dataset: ValidationDataset | None = None,
) -> ValidationCase:
    def path_value(key: str) -> Path:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InvalidInputError(f"validation case {case_id!r} needs {key}")
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

    mode = str(raw.get("mode", "self"))
    if mode not in {"self", "cross"}:
        raise InvalidInputError(
            f"validation case {case_id!r} mode must be 'self' or 'cross'"
        )
    receptors, receptor_names, structure_kinds = _receptors_from_dict(
        raw, base, case_id
    )
    if mode == "cross" and len(receptors) < 2:
        raise InvalidInputError(
            f"validation case {case_id!r} cross mode needs at least two receptors"
        )
    receptor = (
        path_value("receptor")
        if isinstance(raw.get("receptor"), str) and raw.get("receptor", "").strip()
        else (receptors[0] if receptors else None)
    )
    if receptor is None:
        raise InvalidInputError(f"validation case {case_id!r} needs receptor")

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

    source = ""
    license_id = ""
    redistributable: bool | None = None
    local_only = False
    source_url = ""
    accessed_at = ""
    source_sha256 = ""
    target_family = str(raw.get("targetFamily", ""))
    ligand_chain = str(raw.get("ligandChain", ""))
    ligand_residue = str(raw.get("ligandResidue", ""))
    if version != LEGACY_MANIFEST_VERSION:
        source = _required_text(raw, "source", case_id)
        license_id = _required_text(raw, "license", case_id)
        redistributable = _required_bool(raw, "redistributable", case_id)
        local_only = _required_bool(raw, "localOnly", case_id) if "localOnly" in raw else False
        source_url = _required_text(raw, "sourceUrl", case_id)
        accessed_at = _required_text(raw, "accessedAt", case_id)
        if not _DATE_RE.fullmatch(accessed_at):
            raise InvalidInputError(
                f"validation case {case_id!r} accessedAt must use YYYY-MM-DD"
            )
        source_sha256 = _required_text(raw, "sourceSha256", case_id)
        if not _SHA256_RE.fullmatch(source_sha256):
            raise InvalidInputError(
                f"validation case {case_id!r} sourceSha256 must be a 64-character hex digest"
            )
        _validate_license(case_id, license_id, redistributable, local_only)

    return ValidationCase(
        id=case_id,
        name=str(raw.get("name") or case_id),
        receptor=receptor,
        ligand=path_value("ligand"),
        reference=path_value("reference"),
        mode=mode,
        receptors=receptors,
        receptor_names=receptor_names,
        structure_kinds=structure_kinds,
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
        default_altloc=str(raw.get("defaultAltloc", "")),
        keep_hetero=_string_tuple(raw.get("keepHetero"), "keepHetero", case_id),
        box_source=str(raw.get("boxSource", "")),
        official_posebusters=bool(raw.get("officialPoseBusters", False)),
        reference_source=str(raw.get("referenceSource", "")),
        dataset=dataset.id if dataset is not None else "legacy",
        source=source,
        license=license_id,
        redistributable=redistributable,
        local_only=local_only,
        source_url=source_url,
        accessed_at=accessed_at,
        source_sha256=source_sha256,
        target_family=target_family,
        ligand_chain=ligand_chain,
        ligand_residue=ligand_residue,
    )


def _string_tuple(value: Any, key: str, case_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise InvalidInputError(
            f"validation case {case_id!r} {key} must be a list of residue keys"
        )
    return tuple(item.strip() for item in value)


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
    paths = [case.receptor, case.ligand, case.reference, *case.receptors]
    unique = list(dict.fromkeys(paths))
    return [str(path) for path in unique if not path.is_file()]


def receptor_in_reference_frame(receptor_path: Path, reference: Path) -> bool:
    """Cheap coordinate-frame check for cross-docking receptors.

    The closest reference-ligand/receptor atom pair must be within
    :data:`FRAME_MAX_MIN_DISTANCE`. This catches a translated/rotated or
    unrelated receptor, but it is **not** proof that the pocket is the correct
    binding site; it only says the two structures share a frame.
    """
    import numpy as np

    from vinastudio.core.box import points_from_file

    receptor_points = points_from_file(receptor_path)
    reference_points = points_from_file(reference)
    if not receptor_points or not reference_points:
        return False
    receptor_xyz = np.asarray(receptor_points, dtype=float)
    reference_xyz = np.asarray(reference_points, dtype=float)
    distances = ((reference_xyz[:, None, :] - receptor_xyz[None, :, :]) ** 2).sum(axis=2)
    return float(np.sqrt(distances.min())) <= FRAME_MAX_MIN_DISTANCE


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
    reference_unmatched: bool = False,
    reference_independent: bool = True,
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
    if not reference_independent:
        reasons.append("reference is the docking ligand itself; independent redocking is not established")
    if reference_unmatched:
        reasons.append("reference identity could not be verified for reference-relative checks")
    if best_pose_error:
        reasons.append("the best pose has a geometry error")
    if error_poses > 0 and not best_pose_error:
        reasons.append(f"{error_poses} pose(s) have geometry errors")
    if case.affinity_range is not None and best_affinity is not None:
        low, high = case.affinity_range
        if not low <= best_affinity <= high:
            reasons.append(
                f"best affinity {best_affinity:.3f} is outside [{low:.3f}, {high:.3f}]"
            )
    return reasons


def _run_cross_case(
    case: ValidationCase,
    case_dir: Path,
    started: float,
) -> ValidationCaseResult:
    """Dock one ligand into each pre-aligned receptor and report per receptor."""
    ligand = prepare_ligand(case.ligand)
    ligand_path = case_dir / "ligand.pdbqt"
    ligand_path.write_text(ligand.pdbqt, encoding="utf-8")
    ligand_atoms = parse_pdbqt(ligand.pdbqt).first_pose.n_atoms
    box = box_for_case(case)

    receptors = case.receptors or (case.receptor,)
    names = list(case.receptor_names)
    kinds = list(case.structure_kinds)
    while len(names) < len(receptors):
        names.append(f"receptor-{len(names) + 1}")
    while len(kinds) < len(receptors):
        kinds.append("holo")

    representative = DockingParams(
        receptor_path=str(receptors[0]),
        ligand_path=str(ligand_path),
        box_source=case.box_source or "manifest",
        center=box.center,
        size=box.size,
        exhaustiveness=case.exhaustiveness,
        n_poses=case.n_poses,
        seed=case.seed,
        scoring=case.scoring,
    )

    rows: list[dict[str, Any]] = []
    frame_failures: list[str] = []
    for index, receptor_path in enumerate(receptors):
        name = names[index]
        kind = kinds[index]
        row: dict[str, Any] = {
            "index": index,
            "name": name,
            "structureKind": kind,
            "status": "failed",
            "bestRmsd": None,
            "bestAffinity": None,
            "poseCount": 0,
            "errorPoses": 0,
            "outDir": None,
            "error": "",
        }
        rows.append(row)

        if not receptor_in_reference_frame(receptor_path, case.reference):
            frame_failures.append(name)
            row["error"] = "receptor is not in the reference frame"
            continue

        try:
            prepared = prepare_receptor(
                receptor_path,
                ReceptorPrepOptions(
                    allow_bad_residues=case.allow_bad_residues,
                    default_altloc=case.default_altloc,
                    keep_residues=case.keep_hetero,
                ),
            )
            run_dir = case_dir / f"receptor-{index:02d}"
            run_dir.mkdir(parents=True, exist_ok=True)
            receptor_pdbqt = run_dir / "receptor.pdbqt"
            receptor_pdb = run_dir / "receptor.pdb"
            receptor_pdbqt.write_text(prepared.pdbqt, encoding="utf-8")
            receptor_pdb.write_text(prepared.pdb, encoding="utf-8")
            row["outDir"] = str(run_dir)
            row["receptorAtoms"] = parse_pdbqt(prepared.pdbqt).first_pose.n_atoms

            params = replace(representative, receptor_path=str(receptor_pdbqt))
            result = run_docking(params, str(run_dir / "docking"))
            if not result.poses or not result.poses_sdf.strip():
                row["error"] = "docking produced no poses"
                row["warnings"] = list(prepared.report.warnings)
                continue

            poses_path = run_dir / "poses.sdf"
            poses_path.write_text(result.poses_sdf, encoding="utf-8")
            rmsds = rmsd_vs_reference(result.poses_sdf, case.reference)
            findings = validate_poses(result.poses_sdf, reference=case.reference, box=box)
            best_findings = findings[0]
            best_rmsd = rmsds[0] if rmsds else None
            best_error = worst_severity(best_findings) == "error"
            reference_match = reference_matches_poses(result.poses_sdf, case.reference)
            recovered = bool(
                best_rmsd is not None
                and best_rmsd <= case.rmsd_threshold
                and not best_error
                and reference_match is True
            )
            row.update(
                {
                    "status": "passed" if recovered else "failed",
                    "bestRmsd": best_rmsd,
                    "bestAffinity": result.best_affinity,
                    "poseCount": len(result.poses),
                    "errorPoses": sum(
                        1 for pose in findings if worst_severity(pose) == "error"
                    ),
                    "warningPoses": sum(
                        1 for pose in findings if worst_severity(pose) == "warning"
                    ),
                    "checks": [finding.as_dict() for finding in best_findings],
                    "worstCheck": worst_severity(best_findings),
                    "referenceMatched": reference_match,
                    "warnings": list(prepared.report.warnings),
                    "error": "" if reference_match is True else (
                        "reference identity could not be verified"
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001 - one receptor must not stop the case
            row["error"] = f"{type(exc).__name__}: {exc}"

    evaluable = [row for row in rows if row["bestRmsd"] is not None]
    recovered = [row for row in rows if row["status"] == "passed"]
    best_row = min(evaluable, key=lambda row: row["bestRmsd"]) if evaluable else None

    reasons: list[str] = []
    if frame_failures:
        reasons.append(
            "receptor(s) not in the reference frame: " + ", ".join(frame_failures)
        )
    if not evaluable:
        reasons.append("no receptor produced a dockable pose")
    elif not recovered:
        detail = ", ".join(
            f"{row['name']}={row['bestRmsd']:.3f} Å" for row in evaluable
        )
        reasons.append(
            f"no receptor recovered the pose within {case.rmsd_threshold:.3f} Å "
            f"({detail})"
        )
    if (
        best_row is not None
        and case.affinity_range is not None
        and best_row["bestAffinity"] is not None
    ):
        low, high = case.affinity_range
        if not low <= best_row["bestAffinity"] <= high:
            reasons.append(
                f"best affinity {best_row['bestAffinity']:.3f} is outside "
                f"[{low:.3f}, {high:.3f}]"
            )

    official = None
    if case.official_posebusters:
        from vinastudio.core.chem.posebusters_adapter import (
            posebusters_version,
            run_official_posebusters,
        )

        if best_row is not None and best_row.get("outDir"):
            run_dir = Path(str(best_row["outDir"]))
            official = run_official_posebusters(
                (run_dir / "poses.sdf").read_text(encoding="utf-8"),
                case.reference,
                run_dir / "receptor.pdb",
            ).as_dict()
        else:
            official = {
                "status": "not-run",
                "config": "redock",
                "version": posebusters_version(),
                "checks": [],
                "poses": [],
                "summary": {},
                "error": "no evaluable receptor for official PoseBusters",
            }

    cross = {
        "mode": "cross",
        "receptors": rows,
        "evaluable": len(evaluable),
        "recovered": len(recovered),
        "bestReceptor": best_row["name"] if best_row else None,
    }
    redact = case.redistributable is False
    provenance = {
        "inputs": {
            "receptor": _file_info(case.receptor, redact=redact),
            "receptors": [
                {
                    **_file_info(path, redact=redact),
                    "name": names[index],
                    "structureKind": kinds[index],
                }
                for index, path in enumerate(receptors)
            ],
            "ligand": _file_info(case.ligand, redact=redact),
            "reference": _file_info(case.reference, redact=redact),
        },
        "reference": {
            "source": case.reference_source,
            "independentFromLigand": case.reference != case.ligand,
            "matchesDockedPose": (
                best_row.get("referenceMatched") if best_row else None
            ),
        },
        "parameters": _docking_provenance(case, representative, box),
        "receptor": {
            "atoms": best_row.get("receptorAtoms") if best_row else None,
            "warnings": best_row.get("warnings", []) if best_row else [],
        },
        "ligand": {"atoms": ligand_atoms, "warnings": list(ligand.report.warnings)},
        "crossDocking": cross,
    }

    return ValidationCaseResult(
        case=case,
        status="failed" if reasons else "passed",
        reason="; ".join(reasons),
        best_affinity=best_row.get("bestAffinity") if best_row else None,
        best_rmsd=best_row.get("bestRmsd") if best_row else None,
        pose_count=sum(row.get("poseCount", 0) for row in rows),
        receptor_atoms=best_row.get("receptorAtoms") if best_row else None,
        ligand_atoms=ligand_atoms,
        box=box.summary(),
        checks=best_row.get("checks", []) if best_row else [],
        worst_check=best_row.get("worstCheck") if best_row else None,
        error_poses=best_row.get("errorPoses", 0) if best_row else 0,
        warning_poses=best_row.get("warningPoses", 0) if best_row else 0,
        receptor_warnings=best_row.get("warnings", []) if best_row else [],
        ligand_warnings=list(ligand.report.warnings),
        provenance=provenance,
        official_posebusters=official,
        cross_docking=cross,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def run_case(
    case: ValidationCase,
    out_dir: str | Path,
    *,
    exhaustiveness: int | None = None,
    artifact_key: str | None = None,
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
    case_dir = Path(out_dir) / "cases" / (artifact_key or case.id)
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if case.mode == "cross":
        return _run_cross_case(case, case_dir, started)
    try:
        ligand = prepare_ligand(case.ligand)
        receptor = prepare_receptor(
            case.receptor,
            ReceptorPrepOptions(
                allow_bad_residues=case.allow_bad_residues,
                default_altloc=case.default_altloc,
                keep_residues=case.keep_hetero,
            ),
        )
        ligand_path = case_dir / "ligand.pdbqt"
        receptor_path = case_dir / "receptor.pdbqt"
        ligand_path.write_text(ligand.pdbqt, encoding="utf-8")
        receptor_path.write_text(receptor.pdbqt, encoding="utf-8")
        # Official PoseBusters needs a protein structure, not PDBQT; keep the
        # prepared PDB beside the artifacts so the case is self-contained.
        (case_dir / "receptor.pdb").write_text(receptor.pdb, encoding="utf-8")

        box = box_for_case(case)
        params = DockingParams(
            receptor_path=str(receptor_path),
            ligand_path=str(ligand_path),
            box_source=case.box_source
            or ("explicit" if case.center is not None else "reference-autobox"),
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
        reference_match = (
            reference_matches_poses(result.poses_sdf, case.reference)
            if result.poses and result.poses_sdf.strip()
            else None
        )
        redact = case.redistributable is False
        provenance = {
            "inputs": {
                "receptor": _file_info(case.receptor, redact=redact),
                "ligand": _file_info(case.ligand, redact=redact),
                "reference": _file_info(case.reference, redact=redact),
            },
            "reference": {
                "source": case.reference_source,
                "independentFromLigand": case.reference != case.ligand,
                "matchesDockedPose": reference_match,
            },
            "parameters": _docking_provenance(case, params, box),
            "receptor": {"atoms": receptor_atoms, "warnings": list(receptor.report.warnings)},
            "ligand": {"atoms": ligand_atoms, "warnings": list(ligand.report.warnings)},
        }

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
                provenance=provenance,
            )

        (case_dir / "poses.sdf").write_text(result.poses_sdf, encoding="utf-8")
        rmsds = rmsd_vs_reference(result.poses_sdf, case.reference)
        findings = validate_poses(result.poses_sdf, reference=case.reference, box=box)
        best_findings = findings[0]
        error_poses = sum(1 for pose in findings if worst_severity(pose) == "error")
        warning_poses = sum(1 for pose in findings if worst_severity(pose) == "warning")
        best_rmsd = rmsds[0] if rmsds else None
        official = None
        if case.official_posebusters:
            from vinastudio.core.chem.posebusters_adapter import (
                run_official_posebusters,
            )

            official = run_official_posebusters(
                result.poses_sdf,
                case.reference,
                case_dir / "receptor.pdb",
                keep_hetero=case.keep_hetero,
                ligand_residue=case.ligand_residue or None,
            ).as_dict()
        reasons = failure_reasons(
            case,
            pose_count=len(result.poses),
            best_rmsd=best_rmsd,
            best_affinity=result.best_affinity,
            best_pose_error=worst_severity(best_findings) == "error",
            error_poses=error_poses,
            reference_unmatched=reference_match is not True,
            reference_independent=case.reference != case.ligand,
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
            provenance=provenance,
            official_posebusters=official,
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
    seeds: list[int] | None = None,
    dataset: ValidationDataset | None = None,
) -> ValidationReport:
    selected = [case for case in cases if case_ids is None or case.id in case_ids]
    if case_ids is not None:
        unknown = case_ids - {case.id for case in selected}
        if unknown:
            raise InvalidInputError(f"unknown validation case(s): {sorted(unknown)}")
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    results: list[ValidationCaseResult] = []
    for case in selected:
        for seed in seeds or [case.seed]:
            results.append(
                run_case(
                    replace(case, seed=seed),
                    output,
                    exhaustiveness=exhaustiveness,
                    artifact_key=(
                        f"{case.id}-seed{seed}" if seeds is not None else None
                    ),
                )
            )
    return ValidationReport(
        cases=results,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        environment=environment_info(),
        dataset=dataset,
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
    dataset = report.dataset or ValidationDataset(
        id="legacy", name="Legacy 1IEP control", license_summary=(), redistributable=None
    )
    license_summary = ", ".join(dataset.license_summary) or "not recorded"
    redistribution = (
        "yes"
        if dataset.redistributable is True
        else "no" if dataset.redistributable is False else "not recorded"
    )
    lines = [
        "# VinaStudio validation report",
        "",
        f"Report schema: {REPORT_SCHEMA_VERSION}",
        f"Generated: {report.generated_at}",
        f"Dataset: {dataset.id} ({dataset.name})",
        f"Dataset licences: {license_summary}; redistributable: {redistribution}",
        "",
        "This is a reproducible redocking check, not an accuracy ranking. "
        "The project's six geometry checks are a PoseBusters-style subset, not the "
        "official suite. Official PoseBusters results appear separately when the "
        "case enables them; they do not change the project's pass/fail verdict.",
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
        "## Statistics",
        "",
        "| Item | Value |",
        "|---|---:|",
    ]
    stats = _report_statistics(report.cases)
    lines += [
        f"| Evaluable runs | {stats['n']} |",
        f"| Passed | {stats['passed']} |",
        f"| Success rate | {stats['successRate'] if stats['successRate'] is not None else '—'} |",
        f"| Success rate Wilson 95% | {stats['successRateWilson95'] or '—'} |",
        f"| Mean best RMSD (Å) | {stats['meanRmsd'] if stats['meanRmsd'] is not None else '—'} |",
        f"| Median best RMSD (Å) | {stats['medianRmsd'] if stats['medianRmsd'] is not None else '—'} |",
        f"| Mean RMSD bootstrap 95% | {stats['bootstrap95'] or '—'} |",
        "",
        "Descriptive statistics for this dataset; not a universal accuracy claim.",
        "",
        "## Cases",
        "",
        "| Case | Seed | Status | Best affinity | RMSD | Poses | Error poses | Licence | Reason |",
        "|---|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for result in report.cases:
        affinity = "—" if result.best_affinity is None else f"{result.best_affinity:.3f}"
        rmsd = "—" if result.best_rmsd is None else f"{result.best_rmsd:.3f}"
        reason = result.reason.replace("|", "\\|")
        licence = result.case.license or "legacy"
        lines.append(
            f"| {result.case.id} | {result.case.seed} | {result.status} | {affinity} | {rmsd} | "
            f"{result.pose_count} | {result.error_poses} | {licence} | {reason} |"
        )
    cross_cases = [result for result in report.cases if result.cross_docking]
    if cross_cases:
        lines += [
            "",
            "## Cross-docking",
            "",
            "| Case | Seed | Receptor | Kind | Status | Best RMSD | Best affinity | Poses | Error |",
            "|---|---:|---|---|---|---:|---:|---:|---|",
        ]
        for result in cross_cases:
            cross = result.cross_docking or {}
            for row in cross.get("receptors", []):
                rmsd = (
                    "—"
                    if row.get("bestRmsd") is None
                    else f"{row['bestRmsd']:.3f}"
                )
                affinity = (
                    "—"
                    if row.get("bestAffinity") is None
                    else f"{row['bestAffinity']:.3f}"
                )
                error = str(row.get("error") or "").replace("|", "\\|")
                lines.append(
                    f"| {result.case.id} | {result.case.seed} | {row.get('name', '—')} | "
                    f"{row.get('structureKind', '—')} | {row.get('status', '—')} | "
                    f"{rmsd} | {affinity} | {row.get('poseCount', 0)} | {error} |"
                )
        lines += [
            "",
            "Cross-docking requires pre-aligned receptors; the frame check rejects "
            "a receptor whose closest atom to the reference ligand is more than "
            "5 Å away. It is a coordinate sanity check, not a pocket-correctness claim.",
        ]

    official_cases = [
        result
        for result in report.cases
        if result.official_posebusters
        and result.official_posebusters.get("status") == "run"
    ]
    if official_cases:
        lines += [
            "",
            "## Official PoseBusters",
            "",
            "These results are the official suite, run on the same poses and "
            "condition; they are not the project's six checks and do not feed "
            "the pass/fail verdict above.",
            "",
            "| Case | Seed | Poses | Top pose | All poses | Failed checks (top pose) |",
            "|---|---:|---:|---|---|---|",
        ]
        for result in official_cases:
            official = result.official_posebusters or {}
            summary = official.get("summary", {})
            poses = official.get("poses", [])
            top_pose = poses[0] if poses else {}
            failed = ", ".join(top_pose.get("failedChecks", [])) or "—"
            lines.append(
                f"| {result.case.id} | {result.case.seed} | "
                f"{summary.get('poseCount', 0)} | {summary.get('topPassed')} | "
                f"{summary.get('allPosesPassed')} | {failed} |"
            )

    provenance_rows = []
    for result in report.cases:
        prov = result.provenance or {}
        ref = prov.get("reference", {}) if isinstance(prov, dict) else {}
        inputs = prov.get("inputs", {}) if isinstance(prov, dict) else {}
        ref_sdf = inputs.get("reference", {}) if isinstance(inputs, dict) else {}
        provenance_rows.append(
            "| {case} | {independent} | {match} | {sha} |".format(
                case=result.case.id,
                independent=ref.get("independentFromLigand", "—"),
                match=ref.get("matchesDockedPose", "—"),
                sha=str(ref_sdf.get("sha256", "—"))[:12],
            )
        )
    lines += [
        "",
        "## Provenance",
        "",
        "| Case | Reference independent | Reference matches pose | Reference SHA-256 |",
        "|---|---|---|---|",
        *provenance_rows,
        "",
        "A pass means: at least one pose, best RMSD within the configured threshold, "
        "the reference could be matched for reference-relative checks, no geometry "
        "error in any pose, and any configured affinity range met. Warnings are "
        "recorded but do not fail a case. Skipped cases mean their optional input "
        "files are absent; they are not evidence of success. Restricted datasets "
        "are not redistributed with this report.",
        "",
    ]
    return "\n".join(lines)
