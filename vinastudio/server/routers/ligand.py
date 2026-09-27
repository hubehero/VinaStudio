"""Ligand preparation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from vinastudio.core.chem.ligand_prep import (
    LigandPrepOptions,
    inspect_ligand,
    parse_smiles,
    prepare_ligand,
    prepare_ligand_from_smiles,
)
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import create_workspace, slugify
from vinastudio.schemas.preparation import (
    FileRef,
    LigandFromSmilesItem,
    LigandFromSmilesRequest,
    LigandPreparationResponse,
    LigandPrepareRequest,
    LigandPreview,
    LigandReport,
)
from vinastudio.server.routers.artifacts import artifact, run_info

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ligand", tags=["ligand"])


def _to_report(report) -> LigandReport:  # type: ignore[no-untyped-def]
    return LigandReport(
        source=report.source,
        inputFormat=report.input_format,
        inputAtoms=report.input_atoms,
        hydrogensAdded=report.hydrogens_added,
        conformerGenerated=report.conformer_generated,
        geometryOptimised=report.geometry_optimised,
        outputAtoms=report.output_atoms,
        outputPolarHydrogens=report.output_polar_hydrogens,
        nonpolarHydrogensRemoved=report.nonpolar_hydrogens_removed,
        rotatableBonds=report.rotatable_bonds,
        totalCharge=report.total_charge,
        atomTypes=report.atom_types,
        smiles=report.smiles,
        warnings=list(report.warnings),
    )


def _ligand_options(chosen) -> LigandPrepOptions:  # type: ignore[no-untyped-def]
    return LigandPrepOptions(
        optimise_geometry=chosen.optimiseGeometry,
        embed_seed=chosen.embedSeed,
        rigid_macrocycles=chosen.rigidMacrocycles,
        flexible_amides=chosen.flexibleAmides,
        hydrate=chosen.hydrate,
        double_bond_penalty=chosen.doubleBondPenalty,
    )


def _preview_response(preview) -> LigandPreview:  # type: ignore[no-untyped-def]
    return LigandPreview(
        source=preview.source,
        inputFormat=preview.input_format,
        preparable=preview.preparable,
        atoms=preview.atoms,
        hydrogens=preview.hydrogens,
        has3dCoordinates=preview.has_3d_coordinates,
        rotatableBonds=preview.rotatable_bonds,
        molecularFormula=preview.molecular_formula,
        molecularWeight=preview.molecular_weight,
        smiles=preview.smiles,
        records=preview.records,
        notes=list(preview.notes),
    )


@router.post("/inspect", response_model=LigandPreview)
def inspect(request: FileRef) -> LigandPreview:
    """Describe a ligand file before converting it.

    This is what the conversion wizard shows: atoms, whether hydrogens are
    implicit, whether 3D coordinates exist, and how many rotatable bonds docking
    will have to search over.
    """
    preview = inspect_ligand(request.path)
    return _preview_response(preview)


def _collect_smiles(request: LigandFromSmilesRequest) -> list[str]:
    """Normalise single/batch fields into a non-empty list of SMILES strings."""
    entries: list[str] = []
    if request.smiles is not None and request.smiles.strip():
        entries.append(request.smiles.strip())
    if request.smilesList:
        entries.extend(s.strip() for s in request.smilesList if s and s.strip())
    if not entries:
        raise InvalidInputError("provide smiles or a non-empty smilesList")
    if request.name is not None and len(entries) > 1:
        raise InvalidInputError("name applies only to a single SMILES, not a batch")
    return entries


def _unique_sdf_path(directory, slug: str):  # type: ignore[no-untyped-def]
    """``ligands/<slug>.sdf``, appending ``_1``, ``_2``… on collision."""
    candidate = directory / f"{slug}.sdf"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{slug}_{counter}.sdf"
        counter += 1
    return candidate


@router.post("/from-smiles", response_model=list[LigandFromSmilesItem])
def ligand_from_smiles(request: LigandFromSmilesRequest) -> list[LigandFromSmilesItem]:
    """Build 3D ligands from pasted SMILES (single or one-per-line batch).

    Every SMILES is parsed and parameterised in memory first; only a full
    success writes ``ligands/<slug>.sdf`` and the PDBQT run artefacts, so an
    invalid entry in a batch leaves no half-written files. The written SDF is
    then inspected exactly like a file ligand.
    """
    entries = _collect_smiles(request)
    options = _ligand_options(request.options)

    # Phase 1 — validate every string before any disk write (task §6: no residue).
    for text in entries:
        parse_smiles(text)

    # Phase 2 — prepare in memory. A Meeko failure here also leaves no files.
    prepared: list[tuple[str, object]] = []  # (name, LigandPreparation)
    for index, text in enumerate(entries, start=1):
        if len(entries) == 1 and request.name:
            name = request.name.strip() or f"smiles_{index}"
        else:
            # Literal smiles_N in both locales: an ID, not a translated word (§6).
            name = f"smiles_{index}"
        prepared.append((name, prepare_ligand_from_smiles(text, name, options)))

    from vinastudio.core.workspace import ligands_dir
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    # No active workspace (tests / first launch): fall back to an ephemeral run
    # directory so the endpoint still returns a readable path.
    dest_dir = ligands_dir(ws) if ws is not None else create_workspace("from-smiles").path

    results: list[LigandFromSmilesItem] = []
    for name, prep in prepared:
        sdf_path = _unique_sdf_path(dest_dir, slugify(name, fallback="smiles"))
        sdf_path.write_text(prep.sdf, encoding="utf-8")

        run_ws = create_workspace(f"ligand-{sdf_path.stem}")
        pdbqt_path = run_ws.write(f"{sdf_path.stem}.pdbqt", prep.pdbqt)
        # Second copy under jobs/ so artefact URLs stay inside workspace_root().
        run_sdf_path = run_ws.write(f"{sdf_path.stem}.sdf", prep.sdf)

        preview = inspect_ligand(sdf_path)
        results.append(
            LigandFromSmilesItem(
                path=str(sdf_path),
                name=name,
                bytes=sdf_path.stat().st_size,
                preview=_preview_response(preview),
                preparation=LigandPreparationResponse(
                    run=run_info(run_ws),
                    report=_to_report(prep.report),
                    artifacts=[
                        artifact(run_ws, pdbqt_path, kind="pdbqt"),
                        artifact(run_ws, run_sdf_path, kind="sdf"),
                    ],
                    pdbqt=prep.pdbqt,
                ),
            )
        )

    log.info("built %d ligand(s) from SMILES", len(results))
    return results


@router.post("/prepare", response_model=LigandPreparationResponse)
def prepare(request: LigandPrepareRequest) -> LigandPreparationResponse:
    """Convert a ligand to PDBQT and report every transformation applied.

    The PDBQT is returned inline *and* written to the workspace: it is small
    enough to travel over the API, and having the file on disk keeps a run
    reproducible.
    """
    chosen = request.options
    workspace = create_workspace(f"ligand-{request.path}")

    result = prepare_ligand(request.path, _ligand_options(chosen))

    stem = workspace.path.name
    pdbqt_path = workspace.write(f"{stem}.pdbqt", result.pdbqt)
    sdf_path = workspace.write(f"{stem}.sdf", result.sdf)

    log.info(
        "prepared ligand %s: %d atoms -> %d, %d rotatable bonds",
        request.path,
        result.report.input_atoms,
        result.report.output_atoms,
        result.report.rotatable_bonds,
    )

    return LigandPreparationResponse(
        run=run_info(workspace),
        report=_to_report(result.report),
        artifacts=[
            artifact(workspace, pdbqt_path, kind="pdbqt"),
            artifact(workspace, sdf_path, kind="sdf"),
        ],
        pdbqt=result.pdbqt,
    )
