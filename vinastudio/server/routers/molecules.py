"""Molecule manifest endpoints: load, save, delete, clear, verify.

The manifest is a workspace-level ``molecules.json`` file that persists
the full molecule list across sessions.  It is separate from project
files because a workspace can serve multiple projects.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from vinastudio.core.errors import InvalidInputError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/molecules", tags=["molecules"])


def _get_workspace() -> Path:
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    if ws is None:
        raise InvalidInputError("no workspace configured")
    return ws


# ── endpoints ────────────────────────────────────────────────────────────────


@router.get("")
def list_molecules() -> dict:
    """Return the full molecule manifest."""
    from vinastudio.core.workspace import load_molecule_manifest

    ws = _get_workspace()
    return load_molecule_manifest(ws)


@router.post("/save")
def save_molecules(request: dict) -> dict:
    """Save the molecule manifest.

    Expects a JSON body that is a ``MoleculeManifest`` object.
    """
    from vinastudio.core.workspace import save_molecule_manifest

    ws = _get_workspace()
    save_molecule_manifest(ws, request)
    molecules = request.get("molecules", [])
    return {"status": "saved", "count": len(molecules)}


@router.delete("/{mol_id}")
def delete_molecule(mol_id: str) -> dict:
    """Remove a single molecule from the manifest by ID."""
    from vinastudio.core.workspace import load_molecule_manifest, save_molecule_manifest

    ws = _get_workspace()
    manifest = load_molecule_manifest(ws)
    before = len(manifest.get("molecules", []))
    manifest["molecules"] = [m for m in manifest.get("molecules", []) if m.get("id") != mol_id]
    after = len(manifest["molecules"])
    if before == after:
        raise InvalidInputError(f"molecule not found: {mol_id}")
    save_molecule_manifest(ws, manifest)
    return {"status": "deleted", "count": after}


@router.post("/clear")
def clear_molecules() -> dict:
    """Empty the molecule manifest."""
    from vinastudio.core.workspace import save_molecule_manifest

    ws = _get_workspace()
    save_molecule_manifest(ws, {"formatVersion": "1.0", "molecules": []})
    return {"status": "cleared", "count": 0}


@router.post("/verify")
def verify_molecules(request: dict) -> dict:
    """Check which molecule files still exist on disk.

    Expects ``{"ids": ["id1", ...]}`` and returns which exist/are missing.
    Also returns per-molecule mtime for staleness detection.
    """
    from vinastudio.core.workspace import load_molecule_manifest

    ws = _get_workspace()
    manifest = load_molecule_manifest(ws)
    ids = set(request.get("ids", []))
    molecules = {m["id"]: m for m in manifest.get("molecules", []) if m["id"] in ids}

    existing = []
    missing = []
    mtimes = {}
    for mol_id in ids:
        mol = molecules.get(mol_id)
        if mol is None:
            missing.append(mol_id)
            continue
        path = Path(mol.get("path", ""))
        if path.is_file():
            existing.append(mol_id)
            mtimes[mol_id] = path.stat().st_mtime
        else:
            missing.append(mol_id)

    return {"existing": existing, "missing": missing, "mtimes": mtimes}


@router.delete("/{mol_id}/file")
def delete_molecule_file(mol_id: str) -> dict:
    """Delete the physical file for a molecule, if it's workspace-managed.

    Only deletes files under the workspace's ``receptors/`` or ``ligands/``
    directories (i.e., uploaded via browser).  External files (native paths,
    library downloads in ``jobs/``) are not touched.
    """
    from vinastudio.core.workspace import load_molecule_manifest

    ws = _get_workspace()
    manifest = load_molecule_manifest(ws)
    mol = next((m for m in manifest.get("molecules", []) if m.get("id") == mol_id), None)
    if mol is None:
        raise InvalidInputError(f"molecule not found: {mol_id}")

    path = Path(mol.get("path", ""))
    ws_resolved = ws.resolve()
    try:
        path_resolved = path.resolve()
    except OSError:
        raise InvalidInputError(f"invalid path: {path}") from None

    # Only delete if the file is inside the workspace's receptors/ or ligands/.
    in_receptors = path_resolved.is_relative_to(ws_resolved / "receptors")
    in_ligands = path_resolved.is_relative_to(ws_resolved / "ligands")
    if not (in_receptors or in_ligands):
        return {"deleted": False, "reason": "external_path"}

    if path.is_file():
        path.unlink()
        return {"deleted": True}
    return {"deleted": False, "reason": "not_found"}
