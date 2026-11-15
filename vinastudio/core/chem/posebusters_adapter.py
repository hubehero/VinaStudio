"""Optional official PoseBusters integration.

The project's six geometry checks and the official PoseBusters suite are
separate instruments. This module never changes the project's findings; it
returns an independent result that callers may report alongside them.

`posebusters` is an optional dependency (``uv sync --extra analysis``). When it
is absent, every entry point returns ``status="not-run"`` instead of raising:
the desktop application must start and validate poses without it.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PoseBustersStatus = Literal["run", "not-run", "partial"]


@dataclass(slots=True)
class OfficialPoseResult:
    """One pose's official PoseBusters outcome."""

    pose: int
    passed: bool
    failed_checks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pose": self.pose,
            "passed": self.passed,
            "failedChecks": list(self.failed_checks),
        }


@dataclass(slots=True)
class OfficialPoseBustersResult:
    """JSON-serialisable result of one official PoseBusters run."""

    status: PoseBustersStatus
    config: str = "redock"
    version: str | None = None
    checks: list[str] = field(default_factory=list)
    poses: list[OfficialPoseResult] = field(default_factory=list)
    error: str | None = None

    @property
    def top_passed(self) -> bool | None:
        return self.poses[0].passed if self.poses else None

    @property
    def all_passed(self) -> bool | None:
        return all(pose.passed for pose in self.poses) if self.poses else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "config": self.config,
            "version": self.version,
            "checks": list(self.checks),
            "poses": [pose.as_dict() for pose in self.poses],
            "summary": {
                "poseCount": len(self.poses),
                "topPassed": self.top_passed,
                "allPosesPassed": self.all_passed,
            },
            "error": self.error,
        }


def posebusters_available() -> bool:
    """True when the optional package can be imported, without importing it."""
    return importlib.util.find_spec("posebusters") is not None


def posebusters_version() -> str | None:
    try:
        return importlib.metadata.version("posebusters")
    except importlib.metadata.PackageNotFoundError:
        return None


def build_condition_pdb(
    receptor_pdb: str | Path,
    *,
    keep_hetero: tuple[str, ...] = (),
    ligand_residue: str | None = None,
    strip_unkept: bool = False,
) -> str:
    """Protein-only condition PDB matching the receptor preparation.

    The prepared receptor PDB is already curated (deleted waters/HETATM are
    gone), so the default keeps its contents and only removes the native ligand
    when its residue name is known. ``strip_unkept=True`` is for a raw receptor
    where waters and non-kept HETATM still need removing, as the offline
    ``scripts/run_posebusters.py`` path does.
    """
    keep = set(keep_hetero)
    lines: list[str] = []
    for line in Path(receptor_pdb).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM", "TER", "END")):
            continue
        if line.startswith("HETATM"):
            residue = line[17:20].strip()
            key = f"{line[21:22].strip()}:{line[22:26].strip()}"
            if ligand_residue is not None and residue == ligand_residue:
                continue
            if strip_unkept and (residue == "HOH" or key not in keep):
                continue
        lines.append(line)
    lines.append("END")
    return "\n".join(lines) + "\n"


def _materialise(value: str | Path, target: Path) -> Path:
    """Return a path for a path-or-text argument.

    ``poses_sdf`` arrives as SDF text from a completed job and as a path from
    the CLI harness. PoseBusters reads files, so text is written to ``target``.
    """
    if isinstance(value, Path):
        return value
    try:
        candidate = Path(value)
        if candidate.is_file():
            return candidate
    except (OSError, ValueError):
        # A multi-kilobyte SDF text is not a path; Path.is_file() raises
        # ENAMETOOLONG instead of returning False on Linux.
        pass
    target.write_text(str(value), encoding="utf-8")
    return target


def run_official_posebusters(
    poses_sdf: str | Path,
    reference_sdf: str | Path,
    receptor_pdb: str | Path,
    *,
    keep_hetero: tuple[str, ...] = (),
    ligand_residue: str | None = None,
    strip_unkept: bool = False,
    config: str = "redock",
) -> OfficialPoseBustersResult:
    """Run official PoseBusters on poses, a crystal reference and a receptor.

    Never raises for a missing optional dependency or a PoseBusters failure:
    the caller reports ``not-run``/``partial`` instead of turning an optional
    instrument into a failed docking job.
    """
    version = posebusters_version()
    if not posebusters_available():
        return OfficialPoseBustersResult(
            status="not-run",
            config=config,
            version=version,
            error="official PoseBusters is not installed",
        )

    try:
        from posebusters import PoseBusters
    except ImportError as exc:  # pragma: no cover - find_spec said it exists
        return OfficialPoseBustersResult(
            status="not-run",
            config=config,
            version=version,
            error=f"official PoseBusters is not importable: {exc}",
        )

    try:
        with tempfile.TemporaryDirectory(prefix="vinastudio-posebusters-") as tmp:
            work = Path(tmp)
            condition = work / "condition.pdb"
            condition.write_text(
                build_condition_pdb(
                    receptor_pdb,
                    keep_hetero=keep_hetero,
                    ligand_residue=ligand_residue,
                    strip_unkept=strip_unkept,
                ),
                encoding="utf-8",
            )
            prediction = _materialise(poses_sdf, work / "poses.sdf")
            truth = _materialise(reference_sdf, work / "reference.sdf")

            frame = PoseBusters(config=config).bust(
                prediction,
                truth,
                condition,
                full_report=False,
            )
            bools = frame.select_dtypes(include=["bool"]).fillna(False)
            checks = [str(column) for column in bools.columns]
            poses: list[OfficialPoseResult] = []
            for index, (_row_index, row) in enumerate(bools.iterrows()):
                failed = [str(column) for column, value in row.items() if not bool(value)]
                poses.append(
                    OfficialPoseResult(
                        pose=index,
                        passed=not failed,
                        failed_checks=failed,
                    )
                )
    except Exception as exc:  # noqa: BLE001 - report the instrument's failure
        return OfficialPoseBustersResult(
            status="partial",
            config=config,
            version=version,
            error=f"{type(exc).__name__}: {exc}",
        )

    return OfficialPoseBustersResult(
        status="run",
        config=config,
        version=version,
        checks=checks,
        poses=poses,
    )
