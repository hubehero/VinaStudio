"""One-way, idempotent import of legacy manifests and screening libraries.

The old files stay in place. They are migration input and an escape hatch,
never a second write target after the catalog exists.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from vinastudio.core.catalog import db, store
from vinastudio.core.catalog.identity import Identity, identity_for_file, ligand_identity
from vinastudio.core.workspace import load_molecule_manifest

log = logging.getLogger(__name__)

_MANIFEST_MARKER = "legacy_manifest_imported"
_LIBRARY_MARKER = "legacy_libraries_imported"


def _backup_manifest(workspace: Path) -> None:
    source = workspace / "molecules.json"
    target = workspace / "molecules.json.pre-catalog"
    if source.is_file() and not target.exists():
        shutil.copy2(source, target)


def _inside(workspace: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _identity_for_entry(entry: dict[str, Any], path: str, kind: str) -> Identity:
    target = Path(path)
    if target.is_file():
        try:
            return identity_for_file(target, kind)
        except (OSError, RuntimeError, ValueError):
            log.debug("catalog migration: could not read identity for %s", path, exc_info=True)
    return Identity(key=f"legacy:{entry.get('id') or content_sha256_text(path)}", kind="legacy")


def content_sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_records(workspace: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(entry.get("assignedType") or entry.get("detectedType") or "unknown")
    files: list[dict[str, Any]] = []
    source = entry.get("path")
    if isinstance(source, str) and source:
        path = Path(source)
        files.append({
            "kind": "source",
            "path": str(path),
            "path_kind": "workspace" if _inside(workspace, path) else "external",
            "is_primary": False,
        })
    for artifact in entry.get("artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        raw_path = artifact.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        files.append({
            "kind": str(artifact.get("kind") or "artifact"),
            "path": str(path),
            "path_kind": "workspace" if _inside(workspace, path) else "external",
            "is_primary": bool(kind == "receptor" and artifact.get("kind") == "pdbqt"),
        })
    return files


def _ensure_collection(conn, name: str) -> str:
    row = conn.execute("SELECT id FROM collections WHERE name = ? LIMIT 1", (name,)).fetchone()
    return str(row["id"]) if row else store.create_collection(conn, name=name)


def _ensure_study(conn, group_id: str, group_name: str | None) -> str:
    study_id = f"study-{group_id}"
    row = conn.execute("SELECT id FROM studies WHERE id = ?", (study_id,)).fetchone()
    if row:
        return str(row["id"])
    pdb_id = None
    if group_name and len(group_name) == 4 and group_name.isalnum():
        pdb_id = group_name.upper()
    now = store._now()
    conn.execute(
        """INSERT INTO studies(id, name, description, source, pdb_id, created_at, updated_at)
           VALUES (?, ?, '', 'legacy-group', ?, ?, ?)""",
        (study_id, group_name or group_id, pdb_id, now, now),
    )
    return study_id


def _import_manifest(conn, workspace: Path) -> int:
    manifest = load_molecule_manifest(workspace)
    entries = manifest.get("molecules", []) if isinstance(manifest, dict) else []
    if not entries:
        return 0
    imported = 0
    group_studies: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        path = str(entry["path"])
        kind = str(entry.get("assignedType") or entry.get("detectedType") or "unknown")
        identity = _identity_for_entry(entry, path, kind)
        aliases = entry.get("aliases") or []
        category = entry.get("category")
        tags = [category] if isinstance(category, str) and category.strip() else []
        mol_id, _ = store.upsert_molecule(
            conn,
            name=str(entry.get("name") or Path(path).name),
            identity=identity,
            kind_hint=kind,
            source="legacy",
            source_id=str(entry.get("id") or ""),
            metadata={"legacyStatus": entry.get("status")},
            files=_file_records(workspace, entry),
            aliases=aliases,
            tags=tags,
            molecule_id=str(entry.get("id")) if entry.get("id") else None,
        )
        if category:
            collection = _ensure_collection(conn, str(category))
            store.add_collection_member(conn, collection, mol_id)
        group_id = entry.get("groupId")
        if group_id:
            study_id = group_studies.get(str(group_id))
            if study_id is None:
                study_id = _ensure_study(conn, str(group_id), entry.get("groupName"))
                group_studies[str(group_id)] = study_id
            role = "receptor" if kind == "receptor" else "ligand"
            store.add_study_member(
                conn,
                study_id,
                mol_id,
                role=role,
                is_primary=role == "receptor",
            )
        imported += 1
    return imported


def _import_libraries(conn, workspace: Path) -> int:
    root = workspace / "libraries"
    if not root.is_dir():
        return 0
    imported = 0
    for library_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        index_path = library_dir / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries = index.get("entries", []) if isinstance(index, dict) else []
        if not entries:
            continue
        library_name = str(index.get("name") or library_dir.name)
        library_id = f"lib-legacy-{library_dir.name}"
        exists = conn.execute("SELECT id FROM libraries WHERE id = ?", (library_id,)).fetchone()
        if exists is None:
            now = store._now()
            conn.execute(
                """INSERT INTO libraries(id, name, description, source, created_at, updated_at)
                   VALUES (?, ?, ?, 'legacy-library', ?, ?)""",
                (library_id, library_name, "Imported from the pre-catalog SDF library", now, now),
            )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            relative = entry.get("file")
            if not isinstance(relative, str):
                continue
            sdf_path = library_dir / relative
            if not sdf_path.is_file():
                continue
            try:
                identity = ligand_identity(sdf_path)
            except (OSError, RuntimeError, ValueError):
                continue
            index_number = int(entry.get("index") or 0)
            pdbqt = library_dir / "mols" / f"{index_number:06d}.pdbqt"
            mol_id, _ = store.upsert_molecule(
                conn,
                name=str(entry.get("name") or sdf_path.name),
                identity=identity,
                kind_hint="ligand",
                source="legacy-library",
                source_id=library_name,
                files=[{
                    "kind": "source",
                    "path": str(sdf_path),
                    "path_kind": "workspace",
                    "is_primary": True,
                }],
            )
            store.add_library_member(
                conn,
                library_id,
                mol_id,
                entry_index=index_number,
                prepared_path=str(pdbqt) if pdbqt.is_file() else None,
            )
            imported += 1
    return imported


def import_legacy(workspace: Path, db_path: Path | None = None) -> dict[str, Any]:
    """Import manifest + legacy libraries once; safe to call repeatedly."""
    _backup_manifest(workspace)
    with db.transaction(db_path) as conn:
        manifest_done = conn.execute(
            "SELECT value FROM catalog_meta WHERE key = ?", (_MANIFEST_MARKER,)
        ).fetchone()
        imported_manifest = 0 if manifest_done else _import_manifest(conn, workspace)
        if not manifest_done:
            conn.execute(
                "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES (?, '1')",
                (_MANIFEST_MARKER,),
            )

        library_done = conn.execute(
            "SELECT value FROM catalog_meta WHERE key = ?", (_LIBRARY_MARKER,)
        ).fetchone()
        imported_libraries = 0 if library_done else _import_libraries(conn, workspace)
        if not library_done:
            conn.execute(
                "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES (?, '1')",
                (_LIBRARY_MARKER,),
            )
    return {
        "manifest": imported_manifest,
        "libraries": imported_libraries,
        "skippedManifest": bool(manifest_done),
        "skippedLibraries": bool(library_done),
    }
