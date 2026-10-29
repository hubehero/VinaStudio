"""Molecule Catalog API: search, metadata, Studies, Collections, Libraries."""

from __future__ import annotations

import logging
import mimetypes
import sqlite3
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from vinastudio.core.catalog import db, migrate, query, store, suggest
from vinastudio.core.catalog.identity import identity_for_file
from vinastudio.core.catalog.library import invalidate_library_materialization, materialize_library
from vinastudio.core.chem.detect import detect_kind
from vinastudio.core.chem.preview import renderable_ligand_3d
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import resolve_within
from vinastudio.schemas.catalog import (
    CatalogMoleculeOut,
    CatalogPrepareRequest,
    CatalogSearchOut,
    CollectionCreate,
    CollectionOut,
    CollectionPatch,
    ImportRequest,
    LibraryCreate,
    LibraryMemberAdd,
    LibraryOut,
    SavedViewCreate,
    SavedViewOut,
    SelectionCreate,
    SelectionOut,
    StudyCreate,
    StudyMemberAdd,
    StudyOut,
    StudyPatch,
    SuggestionOut,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/catalog", tags=["catalog"])

# The legacy import is a one-time workspace migration, not a per-request step.
# Keep it process-local: the marker rows make it safe to retry, while a catalog
# read must not take the global write lock just to re-run schema/seed checks.
_READY: set[Path] = set()
_READY_LOCK = threading.Lock()


def _ready() -> Path:
    from vinastudio.server.routers.workspace import get_active_workspace

    workspace = get_active_workspace()
    if workspace is None:
        raise InvalidInputError("no workspace configured")
    path = db.catalog_path()
    with _READY_LOCK:
        if path not in _READY:
            migrate.import_legacy(workspace, path)
            _READY.add(path)
    return path


def _workspace_or_none():
    from vinastudio.server.routers.workspace import get_active_workspace

    return get_active_workspace()


def _detail(conn, molecule_id: str) -> dict[str, Any]:
    detail = store.get_molecule(conn, molecule_id)
    if detail is None:
        raise InvalidInputError(f"molecule not found: {molecule_id}")
    return detail


@router.get("/summary")
def summary() -> dict[str, Any]:
    with db.transaction(_ready()) as conn:
        return store.summary(conn)


@router.get("/molecules", response_model=CatalogSearchOut)
def search_molecules(
    q: str = "",
    limit: int = Query(default=query.DEFAULT_LIMIT, ge=1, le=query.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    sort: str = "updated",
    kind: str | None = None,
    status: str | None = None,
    source: str | None = None,
    tag: str | None = None,
    study_id: str | None = None,
    collection_id: str | None = None,
    library_id: str | None = None,
    role: str | None = None,
    mw_min: float | None = None,
    mw_max: float | None = None,
    qed: str | None = None,
    tpsa: str | None = None,
    logp: str | None = None,
    hbd: str | None = None,
    hba: str | None = None,
    rotatable: str | None = None,
    prep: str | None = None,
    unassigned: bool = False,
) -> dict[str, Any]:
    db_path = _ready()
    filters = {
        key: value
        for key, value in {
            "kind": kind,
            "status": status,
            "source": source,
            "tag": tag,
            "study_id": study_id,
            "collection_id": collection_id,
            "library_id": library_id,
            "role": role,
            "mw_min": mw_min,
            "mw_max": mw_max,
            "qed": qed,
            "tpsa": tpsa,
            "logp": logp,
            "hbd": hbd,
            "hba": hba,
            "rotatable": rotatable,
            "prep_status": prep,
            "unassigned": unassigned,
        }.items()
        if value not in (None, False, "")
    }
    result = query.search_molecules(
        q=q, filters=filters, limit=limit, offset=offset, sort=sort, db_path=db_path
    )
    with db.connect(db_path) as conn:
        details = store.get_molecules(conn, [item["id"] for item in result["items"]])
        by_id = {item["id"]: item for item in details}
        enriched = [by_id.get(item["id"], item) for item in result["items"]]
    return {
        "items": enriched,
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
        "facets": result["facets"],
    }


@router.get("/molecules/ids")
def matching_molecule_ids(
    q: str = "",
    kind: str | None = None,
    status: str | None = None,
    source: str | None = None,
    tag: str | None = None,
    study_id: str | None = None,
    collection_id: str | None = None,
    library_id: str | None = None,
    role: str | None = None,
    mw_min: float | None = None,
    mw_max: float | None = None,
    qed: str | None = None,
    tpsa: str | None = None,
    logp: str | None = None,
    hbd: str | None = None,
    hba: str | None = None,
    rotatable: str | None = None,
    prep: str | None = None,
    unassigned: bool = False,
) -> dict[str, list[str]]:
    filters = {
        key: value
        for key, value in {
            "kind": kind,
            "status": status,
            "source": source,
            "tag": tag,
            "study_id": study_id,
            "collection_id": collection_id,
            "library_id": library_id,
            "role": role,
            "mw_min": mw_min,
            "mw_max": mw_max,
            "qed": qed,
            "tpsa": tpsa,
            "logp": logp,
            "hbd": hbd,
            "hba": hba,
            "rotatable": rotatable,
            "prep_status": prep,
            "unassigned": unassigned,
        }.items()
        if value not in (None, False, "")
    }
    return {"ids": query.matching_ids(q=q, filters=filters, db_path=_ready())}


@router.post("/molecules/bulk-tags")
def bulk_tags(body: dict[str, Any]) -> dict[str, int]:
    ids = [str(item) for item in body.get("moleculeIds", [])]
    tags = [str(item) for item in body.get("addTags", [])]
    with db.transaction(_ready()) as conn:
        changed = store.bulk_add_tags(conn, ids, tags)
    return {"changed": changed}


@router.get("/molecules/{molecule_id}", response_model=CatalogMoleculeOut)
def get_molecule(molecule_id: str) -> dict[str, Any]:
    db_path = _ready()
    with db.connect(db_path) as conn:
        return _detail(conn, molecule_id)


@router.patch("/molecules/{molecule_id}", response_model=CatalogMoleculeOut)
def patch_molecule(molecule_id: str, body: dict[str, Any]) -> dict[str, Any]:
    aliases = body.pop("aliases", None)
    tags = body.pop("tags", None)
    patch = {
        "name": body.get("name"),
        "kind_hint": body.get("kindHint", body.get("kind_hint")),
        "status": body.get("status"),
        "prep_status": body.get("prepStatus", body.get("prep_status")),
        "metadata": body.get("metadata"),
    }
    patch = {key: value for key, value in patch.items() if value is not None}
    with db.transaction(_ready()) as conn:
        if patch:
            store.update_molecule(conn, molecule_id, patch)
        if aliases is not None:
            store.set_aliases(conn, molecule_id, aliases)
        if tags is not None:
            store.set_tags(conn, molecule_id, tags)
        return _detail(conn, molecule_id)


@router.delete("/molecules/{molecule_id}")
def delete_molecule(molecule_id: str) -> dict[str, bool]:
    from vinastudio.server.routers.workspace import get_active_workspace

    workspace = get_active_workspace()
    with db.transaction(_ready()) as conn:
        affected_libraries = store.libraries_for_molecule(conn, molecule_id)
        deleted = store.delete_molecule(conn, molecule_id)
    if deleted and workspace is not None:
        for library_id in affected_libraries:
            invalidate_library_materialization(workspace, library_id)
    return {"deleted": deleted}


@router.post("/molecules/{molecule_id}/prepare", response_model=CatalogMoleculeOut)
def prepare_molecule(
    molecule_id: str, request: CatalogPrepareRequest | None = None
) -> dict[str, Any]:
    """Prepare a catalog ligand/receptor with the existing preparation stack.

    The preparation is written through its normal workspace artifacts; the
    catalog records those paths so the molecule becomes usable by the docking
    pipeline and by library materialisation.
    """
    from vinastudio.schemas.preparation import (
        LigandOptions,
        LigandPrepareRequest,
        ReceptorOptions,
        ReceptorPrepareRequest,
    )

    db_path = _ready()
    workspace = _workspace_or_none()
    with db.transaction(db_path) as conn:
        affected_libraries = store.libraries_for_molecule(conn, molecule_id)
        detail = _detail(conn, molecule_id)
        source = next(
            (Path(item["path"]) for item in detail["files"]
             if item["kind"] == "source" and Path(item["path"]).is_file()),
            None,
        )
        if source is None:
            raise InvalidInputError(f"molecule {molecule_id} has no source file")
        kind = detail["kind_hint"]
        if kind == "receptor":
            from vinastudio.server.routers.receptor import prepare as prepare_receptor

            result = prepare_receptor(ReceptorPrepareRequest(
                path=str(source),
                options=(request.receptorOptions if request else None)
                or ReceptorOptions(),
            ))
        elif kind == "ligand":
            from vinastudio.server.routers.ligand import prepare as prepare_ligand

            result = prepare_ligand(LigandPrepareRequest(
                path=str(source),
                options=(request.ligandOptions if request else None) or LigandOptions(),
            ))
        else:
            raise InvalidInputError(f"molecule {molecule_id} has no receptor/ligand role")
        for artifact in result.artifacts:
            store.add_file(
                conn,
                molecule_id,
                kind=artifact.kind,
                path=artifact.path,
                path_kind="workspace",
                bytes_size=artifact.bytes,
            )
        store.update_molecule(conn, molecule_id, {"prep_status": "prepared", "status": "active"})
        pdbqt = next(
            (item.path for item in result.artifacts if item.kind == "pdbqt"),
            None,
        )
        if pdbqt:
            conn.execute(
                "UPDATE library_members SET prepared_path = ? WHERE molecule_id = ?",
                (pdbqt, molecule_id),
            )
        detail = _detail(conn, molecule_id)
    if workspace is not None:
        for library_id in affected_libraries:
            invalidate_library_materialization(workspace, library_id)
    return detail


def _preview_path(detail: dict[str, Any], kind: str) -> Path | None:
    preferred = (
        {"pdb": 0, "cif": 1, "source": 2}
        if kind == "receptor"
        else {"sdf": 0, "mol": 1, "source": 2}
    )
    candidates = sorted(
        detail.get("files", []),
        key=lambda item: preferred.get(str(item.get("kind")), 9),
    )
    allowed = {".pdb", ".cif", ".sdf", ".mol"} if kind == "receptor" else {".sdf", ".mol"}
    for item in candidates:
        path = Path(str(item.get("path") or ""))
        if path.suffix.lower() in allowed and path.is_file():
            return path
    return None


@router.get("/molecules/{molecule_id}/preview")
def molecule_preview(molecule_id: str) -> FileResponse:
    """Serve the renderable source for a Catalog molecule.

    Catalog sources may live outside ``jobs/`` (for example the bundled
    undergraduate library), so they cannot use the artifacts mount. Resolving
    by molecule id keeps this endpoint from accepting an arbitrary path.
    """
    with db.connect(_ready()) as conn:
        detail = store.get_molecule(conn, molecule_id)
    if detail is None:
        raise InvalidInputError(f"molecule not found: {molecule_id}")
    kind = str(detail.get("kind_hint") or "unknown")
    path = _preview_path(detail, kind)
    if path is None:
        raise HTTPException(status_code=404, detail="no renderable source for this molecule")
    return FileResponse(
        str(path),
        media_type=mimetypes.guess_type(str(path))[0],
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/molecules/{molecule_id}/preview3d")
def molecule_preview_3d(molecule_id: str) -> Response:
    """Serve a 3D viewport copy for a ligand, embedding a 2D source if needed."""
    with db.connect(_ready()) as conn:
        detail = store.get_molecule(conn, molecule_id)
    if detail is None:
        raise InvalidInputError(f"molecule not found: {molecule_id}")
    kind = str(detail.get("kind_hint") or "unknown")
    if kind == "receptor":
        raise HTTPException(status_code=404, detail="3D preview is for ligands")
    path = _preview_path(detail, kind)
    if path is None:
        raise HTTPException(status_code=404, detail="no renderable source for this molecule")
    return Response(
        content=renderable_ligand_3d(path),
        media_type="chemical/x-mdl-sdfile",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/molecules/import", response_model=list[CatalogMoleculeOut])
def import_paths(request: ImportRequest) -> list[dict[str, Any]]:
    db_path = _ready()
    imported_ids: list[str] = []
    with db.transaction(db_path) as conn:
        for raw in request.paths:
            path = Path(raw)
            if not path.is_file():
                raise InvalidInputError(f"file not found: {raw}")
            kind = request.kindHint
            if kind == "unknown":
                try:
                    kind = detect_kind(path).kind
                except Exception as exc:
                    raise InvalidInputError(
                        f"cannot classify {path.name}: {exc}"
                    ) from exc
            identity = identity_for_file(path, kind)
            relative = True
            try:
                path.resolve().relative_to(Path(db_path).parent.resolve())
            except ValueError:
                relative = False
            mol_id, _ = store.upsert_molecule(
                conn,
                name=path.name,
                identity=identity,
                kind_hint=kind,
                source="local",
                source_id=path.name,
                files=[{
                    "kind": "source",
                    "path": str(path),
                    "path_kind": "workspace" if relative else "external",
                    "is_primary": True,
                }],
            )
            imported_ids.append(mol_id)
        return [_detail(conn, molecule_id) for molecule_id in imported_ids]


# -- collections ------------------------------------------------------------


@router.get("/collections", response_model=list[CollectionOut])
def list_collections() -> list[dict[str, Any]]:
    with db.connect(_ready()) as conn:
        return store.list_collections(conn)


@router.get("/collections/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: str) -> dict[str, Any]:
    with db.connect(_ready()) as conn:
        collection = store.get_collection(conn, collection_id)
    if collection is None:
        raise InvalidInputError(f"collection not found: {collection_id}")
    return collection


def _validate_collection_parent(conn, collection_id: str | None, parent_id: str | None) -> None:
    """Reject self-parenting and cycles before SQLite accepts a foreign key."""
    if parent_id is None:
        return
    if collection_id is not None and parent_id == collection_id:
        raise InvalidInputError("a collection cannot be its own parent")
    current = parent_id
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            raise InvalidInputError("collection hierarchy contains a cycle")
        seen.add(current)
        row = conn.execute("SELECT parent_id FROM collections WHERE id = ?", (current,)).fetchone()
        if row is None:
            raise InvalidInputError(f"parent collection not found: {parent_id}")
        current = row["parent_id"]


@router.post("/collections", response_model=CollectionOut)
def create_collection(request: CollectionCreate) -> dict[str, Any]:
    with db.transaction(_ready()) as conn:
        _validate_collection_parent(conn, None, request.parentId)
        collection_id = store.create_collection(
            conn,
            name=request.name,
            parent_id=request.parentId,
            description=request.description,
            color=request.color,
            kind=request.kind,
            query=request.query,
        )
        return next(item for item in store.list_collections(conn) if item["id"] == collection_id)


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
def patch_collection(collection_id: str, request: CollectionPatch) -> dict[str, Any]:
    patch = {
        "name": request.name,
        "description": request.description,
        "color": request.color,
        "parent_id": request.parentId,
        "sort_order": request.sortOrder,
        "query": request.query,
    }
    with db.transaction(_ready()) as conn:
        if store.get_collection(conn, collection_id) is None:
            raise InvalidInputError(f"collection not found: {collection_id}")
        if request.parentId is not None:
            _validate_collection_parent(conn, collection_id, request.parentId)
        store.update_collection(
            conn, collection_id, {key: value for key, value in patch.items() if value is not None}
        )
        return next(
            item for item in store.list_collections(conn) if item["id"] == collection_id
        )


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        return {"deleted": store.delete_collection(conn, collection_id)}


@router.post("/collections/{collection_id}/members")
def add_collection_members(collection_id: str, body: dict[str, Any]) -> dict[str, int]:
    ids = list(dict.fromkeys(str(item) for item in body.get("moleculeIds", [])))
    with db.transaction(_ready()) as conn:
        if store.get_collection(conn, collection_id) is None:
            raise InvalidInputError(f"collection not found: {collection_id}")
        existing = {item["id"] for item in store.get_molecules(conn, ids)}
        missing = [molecule_id for molecule_id in ids if molecule_id not in existing]
        if missing:
            raise InvalidInputError(f"molecule not found: {missing[0]}")
        added = sum(store.add_collection_member(conn, collection_id, molecule_id) for molecule_id in ids)
    return {"added": added}


@router.delete("/collections/{collection_id}/members/{molecule_id}")
def remove_collection_member(collection_id: str, molecule_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        removed = store.remove_collection_member(conn, collection_id, molecule_id)
    return {"removed": removed}


# -- studies ----------------------------------------------------------------


@router.get("/studies", response_model=list[StudyOut])
def list_studies() -> list[dict[str, Any]]:
    with db.connect(_ready()) as conn:
        return store.list_studies(conn)


@router.get("/studies/{study_id}", response_model=StudyOut)
def get_study(study_id: str) -> dict[str, Any]:
    with db.connect(_ready()) as conn:
        study = store.get_study(conn, study_id)
    if study is None:
        raise InvalidInputError(f"study not found: {study_id}")
    return study


@router.post("/studies", response_model=StudyOut)
def create_study(request: StudyCreate) -> dict[str, Any]:
    with db.transaction(_ready()) as conn:
        study_id = store.create_study(
            conn,
            name=request.name,
            description=request.description,
            source=request.source,
            pdb_id=request.pdbId,
        )
        return store.get_study(conn, study_id)


@router.patch("/studies/{study_id}", response_model=StudyOut)
def patch_study(study_id: str, request: StudyPatch) -> dict[str, Any]:
    patch = {
        "name": request.name,
        "description": request.description,
        "pdb_id": request.pdbId,
    }
    with db.transaction(_ready()) as conn:
        store.update_study(
            conn, study_id, {key: value for key, value in patch.items() if value is not None}
        )
        study = store.get_study(conn, study_id)
    if study is None:
        raise InvalidInputError(f"study not found: {study_id}")
    return study


@router.delete("/studies/{study_id}")
def delete_study(study_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        return {"deleted": store.delete_study(conn, study_id)}


@router.post("/studies/{study_id}/members")
def add_study_member(study_id: str, request: StudyMemberAdd) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        if store.get_study(conn, study_id) is None:
            raise InvalidInputError(f"study not found: {study_id}")
        if store.get_molecule(conn, request.moleculeId) is None:
            raise InvalidInputError(f"molecule not found: {request.moleculeId}")
        added = store.add_study_member(
            conn,
            study_id,
            request.moleculeId,
            role=request.role,
            is_primary=request.isPrimary,
        )
    return {"added": added}


@router.post("/studies/{study_id}/primary/{molecule_id}")
def set_study_primary(study_id: str, molecule_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        return {"updated": store.set_primary_receptor(conn, study_id, molecule_id)}


@router.delete("/studies/{study_id}/members/{molecule_id}")
def remove_study_member(study_id: str, molecule_id: str, role: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        removed = store.remove_study_member(conn, study_id, molecule_id, role)
    return {"removed": removed}


# -- libraries --------------------------------------------------------------


@router.get("/libraries", response_model=list[LibraryOut])
def list_libraries() -> list[dict[str, Any]]:
    with db.connect(_ready()) as conn:
        return store.list_libraries(conn)


@router.get("/libraries/{library_id}", response_model=LibraryOut)
def get_library(library_id: str) -> dict[str, Any]:
    with db.connect(_ready()) as conn:
        library = store.get_library(conn, library_id)
    if library is None:
        raise InvalidInputError(f"library not found: {library_id}")
    return library


@router.post("/libraries", response_model=LibraryOut)
def create_library(request: LibraryCreate) -> dict[str, Any]:
    from vinastudio.server.routers.workspace import get_active_workspace

    workspace = get_active_workspace()
    if workspace is None:
        raise InvalidInputError("no workspace configured")
    with db.transaction(_ready()) as conn:
        molecule_ids = list(request.moleculeIds)
        if request.selectionId:
            selection = store.get_selection(conn, request.selectionId)
            if selection is None:
                raise InvalidInputError(f"selection not found: {request.selectionId}")
            members = conn.execute(
                "SELECT molecule_id FROM selection_members WHERE selection_id = ? ORDER BY entry_index",
                (request.selectionId,),
            ).fetchall()
            molecule_ids = [str(row["molecule_id"]) for row in members]
        if not molecule_ids:
            raise InvalidInputError("library has no molecules")
        details = {item["id"]: item for item in store.get_molecules(conn, molecule_ids)}
        missing = [molecule_id for molecule_id in molecule_ids if molecule_id not in details]
        if missing:
            raise InvalidInputError(f"molecule not found: {missing[0]}")
        library_id = store.create_library(conn, name=request.name, description=request.description)
        for index, molecule_id in enumerate(molecule_ids):
            detail = details[molecule_id]
            prepared = next(
                (item["path"] for item in detail["files"] if item["kind"] == "pdbqt"),
                None,
            )
            store.add_library_member(
                conn, library_id, molecule_id, entry_index=index, prepared_path=prepared
            )
        materialize_library(conn, library_id, workspace=workspace)
        return store.get_library(conn, library_id)


@router.patch("/libraries/{library_id}", response_model=LibraryOut)
def patch_library(library_id: str, body: dict[str, Any]) -> dict[str, Any]:
    patch = {
        "name": body.get("name"),
        "description": body.get("description"),
        "source": body.get("source"),
    }
    with db.transaction(_ready()) as conn:
        store.update_library(conn, library_id, {k: v for k, v in patch.items() if v is not None})
        library = store.get_library(conn, library_id)
    if library is None:
        raise InvalidInputError(f"library not found: {library_id}")
    return library


@router.delete("/libraries/{library_id}")
def delete_library(library_id: str) -> dict[str, bool]:
    from vinastudio.core.chem.library import libraries_root
    from vinastudio.server.routers.workspace import get_active_workspace

    workspace = get_active_workspace()
    with db.transaction(_ready()) as conn:
        deleted = store.delete_library(conn, library_id)
    if deleted and workspace is not None:
        try:
            physical = resolve_within(libraries_root(workspace / "libraries"), library_id)
        except ValueError:
            return {"deleted": False}
        if physical.is_dir():
            import shutil

            shutil.rmtree(physical, ignore_errors=True)
    return {"deleted": deleted}


@router.post("/libraries/{library_id}/members")
def add_library_member(library_id: str, request: LibraryMemberAdd) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        if store.get_library(conn, library_id) is None:
            raise InvalidInputError(f"library not found: {library_id}")
        detail = _detail(conn, request.moleculeId)
        index = request.entryIndex
        if index is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(entry_index), -1) + 1 AS n FROM library_members WHERE library_id = ?",
                (library_id,),
            ).fetchone()
            index = int(row["n"])
        prepared = request.preparedPath or next(
            (item["path"] for item in detail["files"] if item["kind"] == "pdbqt"), None
        )
        try:
            added = store.add_library_member(
                conn, library_id, request.moleculeId, entry_index=index, prepared_path=prepared
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="library entry index already exists") from exc
        workspace = _workspace_or_none()
        if workspace is not None:
            materialize_library(conn, library_id, workspace=workspace)
    return {"added": added}


@router.delete("/libraries/{library_id}/members/{molecule_id}")
def remove_library_member(library_id: str, molecule_id: str) -> dict[str, bool]:
    workspace = _workspace_or_none()
    with db.transaction(_ready()) as conn:
        cursor = conn.execute(
            "DELETE FROM library_members WHERE library_id = ? AND molecule_id = ?",
            (library_id, molecule_id),
        )
    if cursor.rowcount and workspace is not None:
        invalidate_library_materialization(workspace, library_id)
    return {"removed": bool(cursor.rowcount)}


# -- suggestions / rebuild --------------------------------------------------


@router.get("/saved-views", response_model=list[SavedViewOut])
def list_saved_views() -> list[dict[str, Any]]:
    with db.connect(_ready()) as conn:
        return store.list_saved_views(conn)


@router.post("/saved-views", response_model=SavedViewOut)
def create_saved_view(request: SavedViewCreate) -> dict[str, Any]:
    with db.transaction(_ready()) as conn:
        return store.create_saved_view(conn, name=request.name, query=request.query)


@router.delete("/saved-views/{view_id}")
def delete_saved_view(view_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        return {"deleted": store.delete_saved_view(conn, view_id)}


# -- selections -------------------------------------------------------------


@router.post("/selections", response_model=SelectionOut)
def create_selection(request: SelectionCreate) -> dict[str, Any]:
    """Resolve a query once and freeze the resulting member snapshot."""
    db_path = _ready()
    spec = request.spec
    if request.moleculeIds:
        with db.connect(db_path) as conn:
            members = []
            seen: set[str] = set()
            for molecule_id in request.moleculeIds:
                if molecule_id in seen:
                    continue
                detail = store.get_molecule(conn, molecule_id)
                if detail is None:
                    raise InvalidInputError(f"molecule not found: {molecule_id}")
                seen.add(molecule_id)
                members.append({
                    "id": molecule_id,
                    "identity_key": str(detail["identity_key"]),
                })
        total = len(members)
        truncated = total > spec.maxMembers
        members = members[: spec.maxMembers]
        source = request.source if request.source != "query" else "ids"
    else:
        filters = dict(spec.filters)
        total = query.matching_count(q=spec.q, filters=filters, db_path=db_path)
        members = query.matching_rows(
            q=spec.q,
            filters=filters,
            limit=min(spec.maxMembers, 50000),
            db_path=db_path,
        )
        truncated = total > spec.maxMembers
        source = request.source
    with db.transaction(db_path) as conn:
        selection_id = store.create_selection(
            conn,
            name=request.name,
            source=source,
            spec=spec.model_dump(),
            members=members,
            truncated=truncated,
        )
        result = store.get_selection(conn, selection_id)
    if result is None:  # pragma: no cover - just inserted
        raise InvalidInputError("could not create selection")
    result["members"] = []
    result["total"] = result["memberCount"]
    return result


@router.get("/selections/{selection_id}", response_model=SelectionOut)
def get_selection(
    selection_id: str,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    with db.connect(_ready()) as conn:
        result = store.get_selection(conn, selection_id)
        if result is None:
            raise InvalidInputError(f"selection not found: {selection_id}")
        members, total = store.list_selection_members(
            conn, selection_id, limit=limit, offset=offset
        )
    result["members"] = members
    result["total"] = total
    return result


@router.delete("/selections/{selection_id}")
def delete_selection(selection_id: str) -> dict[str, bool]:
    with db.transaction(_ready()) as conn:
        return {"deleted": store.delete_selection(conn, selection_id)}


@router.get("/suggestions", response_model=list[SuggestionOut])
def suggestions() -> list[dict[str, Any]]:
    with db.connect(_ready()) as conn:
        return suggest.build_suggestions(conn)


@router.post("/rebuild")
def rebuild_catalog() -> dict[str, Any]:
    workspace = None
    from vinastudio.server.routers.workspace import get_active_workspace

    workspace = get_active_workspace()
    if workspace is None:
        raise InvalidInputError("no workspace configured")
    path = db.catalog_path()
    # Explicit rebuild re-imports legacy sources; the catalog itself is not
    # deleted, so user-created collections/libraries remain.
    return migrate.import_legacy(workspace, path)
