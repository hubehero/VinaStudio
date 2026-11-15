"""Headless docking API: prepare inputs, run Vina, write ``result.json``."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from vinastudio.api.result import build_result_document, write_result_document
from vinastudio.core.box import Box, autobox_from_file
from vinastudio.core.chem.ligand_prep import (
    LigandPreparation,
    LigandPrepOptions,
    prepare_ligand,
)
from vinastudio.core.chem.receptor_prep import (
    ReceptorPreparation,
    ReceptorPrepOptions,
    prepare_receptor,
)
from vinastudio.core.docking import DockingParams, run_docking
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.stdio import engine_output_to_stderr
from vinastudio.schemas.job import JobConfig
from vinastudio.schemas.result import DockResult

#: The job file and the Python API share one config model.
DockConfig = JobConfig


@dataclass(frozen=True, slots=True)
class ResolvedJob:
    """One config with every path resolved against the job file directory."""

    config: JobConfig
    base_dir: Path
    receptor: Path
    ligand: Path
    reference: Path | None
    flex_receptor: Path | None


@dataclass(slots=True)
class DockRun:
    """A completed result document plus the files it points to."""

    result: DockResult
    result_path: Path
    artifacts: dict[str, Path]
    elapsed_ms: int = 0


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate)


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise InvalidInputError(f"{label} not found: {path}")
    return path.resolve()


def resolve_job(config: JobConfig, base_dir: str | Path | None = None) -> ResolvedJob:
    base = Path(base_dir or Path.cwd()).resolve()
    receptor = _require_file(_resolve(base, config.receptor.path), "receptor")
    ligand = _require_file(_resolve(base, config.ligand.path), "ligand")
    reference = (
        _require_file(_resolve(base, config.reference.path), "reference")
        if config.reference is not None
        else None
    )
    flex = (
        _require_file(
            _resolve(base, config.parameters.flexReceptorPath),
            "flexible receptor",
        )
        if config.parameters.flexReceptorPath
        else None
    )
    return ResolvedJob(
        config=config,
        base_dir=base,
        receptor=receptor,
        ligand=ligand,
        reference=reference,
        flex_receptor=flex,
    )


def _receptor_options(config: JobConfig) -> ReceptorPrepOptions:
    options = config.receptor.preparation
    return ReceptorPrepOptions(
        delete_waters=options.deleteWaters,
        delete_hetero=options.deleteHetero,
        allow_bad_residues=options.allowBadResidues,
        normalise_atom_order=options.normaliseAtomOrder,
        default_altloc=options.defaultAltloc,
        keep_residues=tuple(options.keepResidues),
        flexible_residues=tuple(options.flexibleResidues),
    )


def _ligand_options(config: JobConfig) -> LigandPrepOptions:
    options = config.ligand.preparation
    return LigandPrepOptions(
        optimise_geometry=options.optimiseGeometry,
        embed_seed=options.embedSeed,
        rigid_macrocycles=options.rigidMacrocycles,
        flexible_amides=options.flexibleAmides,
        hydrate=options.hydrate,
        double_bond_penalty=options.doubleBondPenalty,
    )


def make_box(config: JobConfig, ligand: Path) -> Box:
    box = config.box
    if box.source == "manual":
        if box.center is None or box.size is None:
            raise InvalidInputError("manual box needs center and size")
        return Box(
            center=box.center,
            size=box.size,
            spacing=box.spacing,
            force_even_voxels=box.forceEvenVoxels,
        )
    derived, _ = autobox_from_file(
        ligand,
        extend=box.extend,
        spacing=box.spacing,
        force_even_voxels=box.forceEvenVoxels,
    )
    return derived


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _copy(source: Path, target: Path) -> Path:
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


def dock(
    config: JobConfig,
    out_dir: str | Path,
    *,
    base_dir: str | Path | None = None,
    command: str = "vinastudio-api dock",
) -> DockRun:
    """Run one headless docking job and write ``<out_dir>/result.json``."""
    job = resolve_job(config, base_dir)
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    receptor_preparation: ReceptorPreparation | None = None
    if job.receptor.suffix.lower() == ".pdbqt":
        receptor_pdbqt = _copy(job.receptor, output / "receptor.pdbqt")
        receptor_pdb: Path | None = None
    else:
        receptor_preparation = prepare_receptor(
            job.receptor, _receptor_options(config)
        )
        receptor_pdbqt = _write_text(
            output / "receptor.pdbqt", receptor_preparation.pdbqt
        )
        receptor_pdb = _write_text(output / "receptor.pdb", receptor_preparation.pdb)

    ligand_preparation: LigandPreparation | None = None
    if job.ligand.suffix.lower() == ".pdbqt":
        ligand_pdbqt = _copy(job.ligand, output / "ligand.pdbqt")
        ligand_sdf: Path | None = None
    else:
        ligand_preparation = prepare_ligand(job.ligand, _ligand_options(config))
        ligand_pdbqt = _write_text(output / "ligand.pdbqt", ligand_preparation.pdbqt)
        ligand_sdf = _write_text(output / "ligand.sdf", ligand_preparation.sdf)

    flex_pdbqt: Path | None = None
    if job.flex_receptor is not None:
        flex_pdbqt = _copy(job.flex_receptor, output / "flex.pdbqt")

    box = make_box(config, job.ligand)
    parameters = config.parameters
    params = DockingParams(
        receptor_path=str(receptor_pdbqt),
        center=box.center,
        size=box.size,
        ligand_path=str(ligand_pdbqt),
        flex_pdbqt_path=str(flex_pdbqt) if flex_pdbqt is not None else None,
        scoring=parameters.scoring,
        exhaustiveness=parameters.exhaustiveness,
        n_poses=parameters.nPoses,
        energy_range=parameters.energyRange,
        min_rmsd=parameters.minRmsd,
        max_evals=parameters.maxEvals,
        cpu=parameters.cpu,
        seed=parameters.seed,
        no_refine=parameters.noRefine,
        verbosity=parameters.verbosity,
        spacing=box.spacing,
        force_even_voxels=box.force_even_voxels,
        box_source=config.box.source,
        engine=parameters.engine,
    )
    # A reused output directory must not leave a stale pose file behind when
    # this run produces none; result.json would otherwise point at old poses.
    for stale in ("poses.pdbqt", "poses.sdf"):
        (output / stale).unlink(missing_ok=True)

    # Vina writes its progress table to file descriptor 1, not sys.stdout.
    with engine_output_to_stderr():
        docking = run_docking(params, str(output))

    poses_pdbqt = output / "poses.pdbqt"
    poses_sdf: Path | None = None
    if docking.poses_sdf:
        poses_sdf = _write_text(output / "poses.sdf", docking.poses_sdf)

    artifacts: dict[str, Path | None] = {
        "receptor_pdbqt": receptor_pdbqt,
        "receptor_pdb": receptor_pdb,
        "ligand_pdbqt": ligand_pdbqt,
        "ligand_sdf": ligand_sdf,
        "poses_pdbqt": poses_pdbqt if poses_pdbqt.is_file() else None,
        "poses_sdf": poses_sdf,
        "flex_pdbqt": flex_pdbqt,
    }
    document = build_result_document(
        config=config,
        receptor_input=job.receptor,
        ligand_input=job.ligand,
        reference=job.reference,
        receptor_preparation=receptor_preparation,
        ligand_preparation=ligand_preparation,
        box=box,
        params=params,
        docking=docking,
        artifacts=artifacts,
        result_dir=output,
        command=command,
    )
    result_path = write_result_document(output / "result.json", document)
    present = {
        name: path
        for name, path in artifacts.items()
        if path is not None and path.is_file()
    }
    return DockRun(
        result=document,
        result_path=result_path,
        artifacts=present,
        elapsed_ms=docking.elapsed_ms,
    )
