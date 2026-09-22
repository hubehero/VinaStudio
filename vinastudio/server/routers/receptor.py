"""Receptor preparation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from vinastudio.core.chem.receptor_prep import (
    ReceptorPrepOptions,
    inspect_receptor,
    prepare_receptor,
)
from vinastudio.core.paths import create_workspace
from vinastudio.schemas.preparation import (
    FileRef,
    ReceptorPreparationResponse,
    ReceptorPrepareRequest,
    ReceptorPreview,
    ReceptorReport,
)
from vinastudio.server.routers.artifacts import artifact, run_info

log = logging.getLogger(__name__)
router = APIRouter(prefix="/receptor", tags=["receptor"])


def _to_report(report) -> ReceptorReport:  # type: ignore[no-untyped-def]
    return ReceptorReport(
        source=report.source,
        inputFormat=report.input_format,
        inputAtoms=report.input_atoms,
        inputResidues=report.input_residues,
        deletedWaters=list(report.deleted_waters),
        deletedHetero=list(report.deleted_hetero),
        normalisedAtomOrder=report.normalised_atom_order,
        validResidues=report.valid_residues,
        ignoredResidues=list(report.ignored_residues),
        flexibleResidues=list(report.flexible_residues),
        outputAtoms=report.output_atoms,
        atomTypes=report.atom_types,
        includeHydrogens=report.include_hydrogens,
        warnings=list(report.warnings),
        residueList=list(report.residue_list),
    )


@router.post("/inspect", response_model=ReceptorPreview)
def inspect(request: FileRef) -> ReceptorPreview:
    """Describe a receptor file, including what would be stripped."""
    preview = inspect_receptor(request.path)
    return ReceptorPreview(
        source=preview.source,
        inputFormat=preview.input_format,
        preparable=preview.preparable,
        atoms=preview.atoms,
        residues=preview.residues,
        chains=preview.chains,
        waters=list(preview.waters),
        hetero=list(preview.hetero),
        residueNames=list(preview.residue_names),
        notes=list(preview.notes),
    )


@router.post("/prepare", response_model=ReceptorPreparationResponse)
def prepare(request: ReceptorPrepareRequest) -> ReceptorPreparationResponse:
    """Parameterise a receptor and write every artefact to the workspace.

    The PDBQT and PDB are *not* returned inline: a receptor is hundreds of
    kilobytes, and the interface fetches them from ``/artifacts`` when the
    renderer needs them.
    """
    chosen = request.options
    workspace = create_workspace(f"receptor-{request.path}")

    result = prepare_receptor(
        request.path,
        ReceptorPrepOptions(
            delete_waters=chosen.deleteWaters,
            delete_hetero=chosen.deleteHetero,
            flexible_residues=tuple(chosen.flexibleResidues),
            allow_bad_residues=chosen.allowBadResidues,
            normalise_atom_order=chosen.normaliseAtomOrder,
        ),
    )

    stem = workspace.path.name
    written = [
        artifact(workspace, workspace.write(f"{stem}.pdbqt", result.pdbqt), kind="pdbqt"),
        artifact(workspace, workspace.write(f"{stem}.pdb", result.pdb), kind="pdb"),
    ]
    if result.flex_pdbqt is not None:
        written.append(
            artifact(
                workspace,
                workspace.write(f"{stem}_flex.pdbqt", result.flex_pdbqt),
                kind="pdbqt",
            )
        )

    log.info(
        "prepared receptor %s: %d residues -> %d atoms",
        request.path,
        result.report.valid_residues,
        result.report.output_atoms,
    )

    return ReceptorPreparationResponse(
        run=run_info(workspace),
        report=_to_report(result.report),
        artifacts=written,
        hasFlexibleSidechains=result.flex_pdbqt is not None,
    )
