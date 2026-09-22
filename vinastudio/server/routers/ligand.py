"""Ligand preparation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from vinastudio.core.chem.ligand_prep import (
    LigandPrepOptions,
    inspect_ligand,
    prepare_ligand,
)
from vinastudio.core.paths import create_workspace
from vinastudio.schemas.preparation import (
    FileRef,
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


@router.post("/inspect", response_model=LigandPreview)
def inspect(request: FileRef) -> LigandPreview:
    """Describe a ligand file before converting it.

    This is what the conversion wizard shows: atoms, whether hydrogens are
    implicit, whether 3D coordinates exist, and how many rotatable bonds docking
    will have to search over.
    """
    preview = inspect_ligand(request.path)
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


@router.post("/prepare", response_model=LigandPreparationResponse)
def prepare(request: LigandPrepareRequest) -> LigandPreparationResponse:
    """Convert a ligand to PDBQT and report every transformation applied.

    The PDBQT is returned inline *and* written to the workspace: it is small
    enough to travel over the API, and having the file on disk keeps a run
    reproducible.
    """
    chosen = request.options
    workspace = create_workspace(f"ligand-{request.path}")

    result = prepare_ligand(
        request.path,
        LigandPrepOptions(
            optimise_geometry=chosen.optimiseGeometry,
            embed_seed=chosen.embedSeed,
            rigid_macrocycles=chosen.rigidMacrocycles,
            flexible_amides=chosen.flexibleAmides,
            hydrate=chosen.hydrate,
            double_bond_penalty=chosen.doubleBondPenalty,
        ),
    )

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
