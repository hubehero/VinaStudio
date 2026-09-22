"""File-level endpoints: dialog filters, inspection, uploads and samples."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from vinastudio.config import SAMPLE_DIR, max_upload_bytes
from vinastudio.core.chem import preview
from vinastudio.core.chem.detect import detect_kind
from vinastudio.core.chem.formats import (
    LIGAND_FILTER,
    LIGAND_SUFFIXES,
    RECEPTOR_FILTER,
    RECEPTOR_SUFFIXES,
)
from vinastudio.core.paths import create_workspace
from vinastudio.schemas.preparation import (
    Artifact,
    DetectionResponse,
    FileFilters,
    FileRef,
    RenderableRequest,
    SampleFile,
    SavedUpload,
)
from vinastudio.server.routers.artifacts import artifact

log = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])

#: Extensions the upload endpoint will accept.
ALLOWED_UPLOAD_SUFFIXES = frozenset(LIGAND_SUFFIXES) | frozenset(RECEPTOR_SUFFIXES)


@router.get("/filters")
def filters() -> FileFilters:
    """The dialog filters and accepted suffixes, defined once in the core."""
    return FileFilters(
        ligand=LIGAND_FILTER,
        receptor=RECEPTOR_FILTER,
        ligandSuffixes=list(LIGAND_SUFFIXES),
        receptorSuffixes=list(RECEPTOR_SUFFIXES),
    )


@router.post("/detect", response_model=DetectionResponse)
def detect(request: FileRef) -> DetectionResponse:
    """Say whether a file holds a receptor or a ligand, from the file itself.

    `.pdb` and `.pdbqt` are used for both, so the answer cannot come from the
    name — and a rule the interface applies privately cannot be tested.
    """
    found = detect_kind(request.path)
    return DetectionResponse(
        kind=found.kind,
        reason=found.reason,
        atoms=found.atoms,
        residues=found.residues,
        waters=found.waters,
        chains=found.chains,
        polymerResidues=found.polymer_residues,
    )


@router.post("/renderable", response_model=list[Artifact])
def renderable(request: RenderableRequest) -> list[Artifact]:
    """Write a copy of a structure that the 3D viewport can draw.

    Loading a molecule should show it: a PDBQT has no bond orders and an mmCIF is
    not renderable at all, so the viewport gets a converted copy straight away
    instead of waiting for the user to prepare the file.
    """
    text, suffix = preview.renderable(request.path, request.kind)

    source = Path(request.path)
    workspace = create_workspace(f"render-{source.stem}")
    target = workspace.write(f"{source.stem or 'structure'}.{suffix}", text)
    return [artifact(workspace, target, kind=suffix)]


@router.post("/upload", response_model=SavedUpload)
async def upload(file: UploadFile = File(...)) -> SavedUpload:
    """Accept a dropped file.

    Native drag-and-drop into QWebEngine hands the page a File object with no
    filesystem path, so the bytes have to come through HTTP instead of being
    read in place. Files land in a workspace directory and are then treated
    exactly like a path picked through the native dialog.
    """
    name = Path(file.filename or "upload").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"{suffix or 'unknown extension'} is not a supported molecule format",
        )

    # Check file size before reading into memory
    max_bytes = max_upload_bytes()
    content_length = file.size
    if content_length is not None and content_length > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {content_length} bytes exceeds limit of {max_mb} MB",
        )

    workspace = create_workspace(f"upload-{name}")
    target = workspace.file(name)
    payload = await file.read()

    # Double-check after reading (Content-Length may be missing or lying)
    if len(payload) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {len(payload)} bytes exceeds limit of {max_mb} MB",
        )

    if not payload:
        raise HTTPException(status_code=400, detail="the uploaded file is empty")
    target.write_bytes(payload)

    log.info("stored upload %s (%d bytes) in %s", name, len(payload), workspace.run_id)
    return SavedUpload(
        path=str(target),
        name=name,
        bytes=len(payload),
        suffix=suffix,
    )


@router.get("/samples", response_model=list[SampleFile])
def samples() -> list[SampleFile]:
    """The bundled 1iep example, if it has been fetched."""
    directory = SAMPLE_DIR / "1iep"
    if not directory.is_dir():
        return []

    descriptions = {
        "1iep_receptorH.pdb": "c-Abl kinase domain, protonated (receptor input)",
        "1iep_ligand.sdf": "imatinib with 3D coordinates (ligand input)",
        "1iep_ligand.pdbqt": "imatinib prepared by Meeko (docking input)",
        "1iep_ligand_vina_out.pdbqt": "four docked poses (results input)",
        "1iep_receptor.pdbqt": "receptor prepared by upstream Meeko",
    }
    found = [
        SampleFile(
            name=path.name,
            path=str(path),
            description=descriptions.get(path.name, ""),
            bytes=path.stat().st_size,
        )
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() != ".md"
    ]
    return found
