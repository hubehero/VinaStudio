"""Build and read the headless result document from core objects."""

from __future__ import annotations

import json
import os
import platform
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from vinastudio import __version__
from vinastudio.core.box import Box
from vinastudio.core.chem.ligand_prep import LigandPreparation
from vinastudio.core.chem.pose_validation import validate_poses, worst_severity
from vinastudio.core.chem.receptor_prep import ReceptorPreparation
from vinastudio.core.chem.rmsd import reference_matches_poses, rmsd_vs_reference
from vinastudio.core.docking import DockingParams, DockingResult
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.provenance import environment_info, file_info, git_metadata
from vinastudio.schemas.job import JobConfig
from vinastudio.schemas.result import (
    Artifacts,
    DockResult,
    EngineInfo,
    FindingRecord,
    InputFile,
    InputFiles,
    PoseRecord,
    PreparationBlock,
    ProjectChecks,
    Provenance,
    ReferenceValidation,
    ResultParameters,
    SearchSpace,
    SoftwareInfo,
    ValidationBlock,
)


def _input_file(path: Path) -> InputFile:
    info = file_info(path, relative_to_root=False)
    if not info.get("exists"):
        raise InvalidInputError(f"input file not found: {path}")
    return InputFile(
        path=str(info["path"]),
        sha256=str(info["sha256"]),
        format=str(info["format"]),
        bytes=int(info["bytes"]),
    )


def _preparation_block(
    preparation: ReceptorPreparation | LigandPreparation | None,
    source: Path,
) -> dict[str, Any]:
    if preparation is not None:
        return asdict(preparation.report)
    return {
        "source": str(source),
        "inputFormat": source.suffix.lower().lstrip("."),
        "preparedInput": True,
        "warnings": [],
    }


def _relative(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _pose_checks(
    docking: DockingResult,
    reference: Path | None,
    box: Box,
) -> list[list[FindingRecord]]:
    if not docking.poses_sdf.strip():
        return []
    findings = validate_poses(docking.poses_sdf, reference, box=box)
    return [
        [FindingRecord(**finding.as_dict()) for finding in group]
        for group in findings
    ]


def build_result_document(
    *,
    config: JobConfig,
    receptor_input: Path,
    ligand_input: Path,
    reference: Path | None,
    receptor_preparation: ReceptorPreparation | None,
    ligand_preparation: LigandPreparation | None,
    box: Box,
    params: DockingParams,
    docking: DockingResult,
    artifacts: dict[str, Path | None],
    result_dir: Path,
    command: str,
) -> DockResult:
    """Assemble the result contract without re-running any science."""
    checks = _pose_checks(docking, reference, box)
    rmsds = (
        rmsd_vs_reference(docking.poses_sdf, reference)
        if reference is not None and docking.poses_sdf.strip()
        else []
    )
    matched = (
        reference_matches_poses(docking.poses_sdf, reference)
        if reference is not None and docking.poses_sdf.strip()
        else None
    )

    poses: list[PoseRecord] = []
    for index, pose in enumerate(docking.poses):
        pose_checks = checks[index] if index < len(checks) else []
        poses.append(
            PoseRecord(
                rank=pose.index,
                affinity=pose.affinity,
                rmsdLower=pose.rmsd_lower,
                rmsdUpper=pose.rmsd_upper,
                rmsdToReference=rmsds[index] if index < len(rmsds) else None,
                worstCheck=worst_severity(pose_checks),
                checks=pose_checks,
            )
        )

    all_checks = [finding for group in checks for finding in group]
    environment = environment_info()
    flex_artifact = artifacts.get("flex_pdbqt")

    return DockResult(
        software=SoftwareInfo(version=str(__version__)),
        engine=EngineInfo(
            name="vina",
            version=environment.get("vina", "unknown"),
            backend=environment.get("engineBackend", "unknown"),
            scoring=params.scoring,
        ),
        inputs=InputFiles(
            receptor=_input_file(receptor_input),
            ligand=_input_file(ligand_input),
            reference=_input_file(reference) if reference is not None else None,
        ),
        preparation=PreparationBlock(
            receptor=_preparation_block(receptor_preparation, receptor_input),
            ligand=_preparation_block(ligand_preparation, ligand_input),
        ),
        searchSpace=SearchSpace(
            center=box.center,
            size=box.size,
            spacing=box.spacing,
            forceEvenVoxels=box.force_even_voxels,
            source=config.box.source,
            sourceDetail=(
                "manual center/size"
                if config.box.source == "manual"
                else f"autobox from {ligand_input.name}"
            ),
        ),
        parameters=ResultParameters(
            scoring=params.scoring,
            exhaustiveness=params.exhaustiveness,
            nPoses=params.n_poses,
            energyRange=params.energy_range,
            minRmsd=params.min_rmsd,
            maxEvals=params.max_evals,
            cpu=params.cpu,
            seed=params.seed,
            noRefine=params.no_refine,
            engine=params.engine,
            verbosity=params.verbosity,
            flexReceptorPath=_relative(flex_artifact, result_dir),
        ),
        artifacts=Artifacts(
            receptorPdbqt=_relative(artifacts.get("receptor_pdbqt"), result_dir),
            receptorPdb=_relative(artifacts.get("receptor_pdb"), result_dir),
            ligandPdbqt=_relative(artifacts.get("ligand_pdbqt"), result_dir),
            ligandSdf=_relative(artifacts.get("ligand_sdf"), result_dir),
            posesPdbqt=_relative(artifacts.get("poses_pdbqt"), result_dir),
            posesSdf=_relative(artifacts.get("poses_sdf"), result_dir),
            flexPdbqt=_relative(flex_artifact, result_dir),
        ),
        poses=poses,
        validation=ValidationBlock(
            reference=(
                ReferenceValidation(path=str(reference.resolve()), matched=matched)
                if reference is not None
                else None
            ),
            projectChecks=ProjectChecks(
                errors=sum(1 for finding in all_checks if finding.severity == "error"),
                warnings=sum(
                    1 for finding in all_checks if finding.severity == "warning"
                ),
                poses=len(docking.poses),
            ),
            posebusters=None,
        ),
        analysis=None,
        provenance=Provenance(
            createdAt=datetime.now(UTC).isoformat(),
            host=platform.node(),
            cwd=str(Path.cwd()),
            command=command,
            environment=environment,
            git=git_metadata(),
        ),
    )


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON through a same-directory temp file and ``os.replace``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def write_result_document(path: str | Path, document: DockResult) -> Path:
    return write_json_atomic(path, document.model_dump(mode="json"))


def read_result_document(path: str | Path) -> DockResult:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InvalidInputError(f"could not read result: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"result is not valid JSON: {exc}") from exc
    try:
        return DockResult.model_validate(payload)
    except ValidationError as exc:
        raise InvalidInputError(f"result does not match the contract: {exc}") from exc


def artifact_path(
    document: DockResult, key: str, result_path: str | Path
) -> Path | None:
    value = getattr(document.artifacts, key)
    if value is None:
        return None
    return (Path(result_path).resolve().parent / value).resolve()
