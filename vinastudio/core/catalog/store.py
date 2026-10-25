"""Catalog CRUD and relationship operations."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vinastudio.core.catalog.identity import Identity, content_sha256

Json = dict[str, Any]


def _now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _json(value: Json | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _recalculate_search_text(conn: sqlite3.Connection, molecule_id: str) -> None:
    row = conn.execute(
        "SELECT name, source, source_id, inchi_key, canonical_smiles FROM molecules WHERE id = ?",
        (molecule_id,),
    ).fetchone()
    if row is None:
        return
    parts = [row["name"], row["source"], row["source_id"], row["inchi_key"], row["canonical_smiles"]]
    parts += [
        alias["alias"]
        for alias in conn.execute(
            "SELECT alias FROM molecule_aliases WHERE molecule_id = ?", (molecule_id,)
        )
    ]
    parts += [
        tag["tag"]
        for tag in conn.execute(
            "SELECT tag FROM molecule_tags WHERE molecule_id = ?", (molecule_id,)
        )
    ]
    parts += [
        item["source"]
        for item in conn.execute(
            "SELECT source FROM molecule_sources WHERE molecule_id = ?", (molecule_id,)
        )
    ]
    parts += [
        item["name"]
        for item in conn.execute(
            """SELECT s.name FROM studies s
               JOIN study_members sm ON sm.study_id = s.id
               WHERE sm.molecule_id = ?""",
            (molecule_id,),
        )
    ]
    parts += [
        item["name"]
        for item in conn.execute(
            """SELECT c.name FROM collections c
               JOIN collection_members cm ON cm.collection_id = c.id
               WHERE cm.molecule_id = ?""",
            (molecule_id,),
        )
    ]
    text = " ".join(str(part) for part in parts if part)
    conn.execute(
        "UPDATE molecules SET search_text = ?, updated_at = ? WHERE id = ?",
        (text, _now(), molecule_id),
    )


def _row_to_molecule(row: sqlite3.Row) -> Json:
    data = dict(row)
    data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
    return data


def add_file(
    conn: sqlite3.Connection,
    molecule_id: str,
    *,
    kind: str,
    path: str | Path,
    path_kind: str = "workspace",
    sha256: str | None = None,
    bytes_size: int | None = None,
    mtime: float | None = None,
    is_primary: bool = False,
) -> str:
    target = Path(path)
    digest = sha256
    if digest is None and target.is_file():
        digest = content_sha256(target)
    size = bytes_size if bytes_size is not None else (target.stat().st_size if target.is_file() else 0)
    file_id = new_id("file")
    conn.execute(
        """INSERT INTO molecule_files
           (id, molecule_id, kind, path, path_kind, sha256, bytes, mtime, is_primary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(molecule_id, path, kind) DO UPDATE SET
             sha256 = COALESCE(excluded.sha256, molecule_files.sha256),
             bytes = CASE WHEN excluded.bytes > 0 THEN excluded.bytes ELSE molecule_files.bytes END,
             mtime = COALESCE(excluded.mtime, molecule_files.mtime),
             is_primary = MAX(molecule_files.is_primary, excluded.is_primary)""",
        (file_id, molecule_id, kind, str(target), path_kind, digest, size, mtime, int(is_primary)),
    )
    return file_id


def set_aliases(conn: sqlite3.Connection, molecule_id: str, aliases: Iterable[str]) -> None:
    conn.execute("DELETE FROM molecule_aliases WHERE molecule_id = ?", (molecule_id,))
    for alias in {str(item).strip() for item in aliases if str(item).strip()}:
        conn.execute(
            "INSERT OR IGNORE INTO molecule_aliases(molecule_id, alias) VALUES (?, ?)",
            (molecule_id, alias),
        )
    _recalculate_search_text(conn, molecule_id)


def set_tags(conn: sqlite3.Connection, molecule_id: str, tags: Iterable[str]) -> None:
    conn.execute("DELETE FROM molecule_tags WHERE molecule_id = ?", (molecule_id,))
    for tag in {str(item).strip() for item in tags if str(item).strip()}:
        conn.execute(
            "INSERT OR IGNORE INTO molecule_tags(molecule_id, tag) VALUES (?, ?)",
            (molecule_id, tag),
        )
    _recalculate_search_text(conn, molecule_id)


def _add_source(
    conn: sqlite3.Connection,
    molecule_id: str,
    source: str,
    source_id: str,
    *,
    url: str | None = None,
    license: str | None = None,
) -> None:
    if not source and not source_id:
        return
    conn.execute(
        """INSERT INTO molecule_sources(molecule_id, source, source_id, url, license)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(molecule_id, source, source_id) DO UPDATE SET
             url = COALESCE(excluded.url, molecule_sources.url),
             license = COALESCE(excluded.license, molecule_sources.license)""",
        (molecule_id, source, source_id, url, license),
    )


def upsert_molecule(
    conn: sqlite3.Connection,
    *,
    name: str,
    identity: Identity,
    kind_hint: str = "unknown",
    source: str = "",
    source_id: str = "",
    source_url: str | None = None,
    license: str | None = None,
    metadata: Json | None = None,
    files: Iterable[dict[str, Any]] = (),
    aliases: Iterable[str] = (),
    tags: Iterable[str] = (),
    molecule_id: str | None = None,
) -> tuple[str, bool]:
    """Insert or merge by identity; returns ``(id, created)``."""
    existing = conn.execute(
        "SELECT id, name, kind_hint, metadata_json FROM molecules WHERE identity_key = ?",
        (identity.key,),
    ).fetchone()
    now = _now()
    if existing is None:
        mol_id = molecule_id or new_id("mol")
        conn.execute(
            """INSERT INTO molecules
               (id, name, kind_hint, source, source_id, identity_key, identity_kind,
                canonical_smiles, inchi_key, parent_inchi_key, formula, molecular_weight,
                status, prep_status, metadata_json, search_text, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'unknown', ?, '', ?, ?)""",
            (
                mol_id,
                name.strip() or "untitled",
                kind_hint,
                source,
                source_id,
                identity.key,
                identity.kind,
                identity.canonical_smiles,
                identity.inchi_key,
                identity.parent_inchi_key,
                identity.formula,
                identity.molecular_weight,
                _json(metadata),
                now,
                now,
            ),
        )
        created = True
    else:
        mol_id = str(existing["id"])
        current_meta = json.loads(existing["metadata_json"] or "{}")
        current_meta.update(metadata or {})
        conn.execute(
            """UPDATE molecules SET
                 name = CASE WHEN name = '' OR name = 'untitled' THEN ? ELSE name END,
                 kind_hint = CASE WHEN kind_hint = 'unknown' THEN ? ELSE kind_hint END,
                 source = CASE WHEN source = '' THEN ? ELSE source END,
                 source_id = CASE WHEN source_id = '' THEN ? ELSE source_id END,
                 canonical_smiles = COALESCE(canonical_smiles, ?),
                 inchi_key = COALESCE(inchi_key, ?),
                 parent_inchi_key = COALESCE(parent_inchi_key, ?),
                 formula = COALESCE(formula, ?),
                 molecular_weight = COALESCE(molecular_weight, ?),
                 metadata_json = ?, updated_at = ?
               WHERE id = ?""",
            (
                name.strip() or "untitled",
                kind_hint,
                source,
                source_id,
                identity.canonical_smiles,
                identity.inchi_key,
                identity.parent_inchi_key,
                identity.formula,
                identity.molecular_weight,
                _json(current_meta),
                now,
                mol_id,
            ),
        )
        created = False

    _add_source(conn, mol_id, source, source_id, url=source_url, license=license)
    for item in files:
        add_file(conn, mol_id, **item)
    if aliases:
        current = {row["alias"] for row in conn.execute(
            "SELECT alias FROM molecule_aliases WHERE molecule_id = ?", (mol_id,)
        )}
        set_aliases(conn, mol_id, current | set(aliases))
    if tags:
        current_tags = {row["tag"] for row in conn.execute(
            "SELECT tag FROM molecule_tags WHERE molecule_id = ?", (mol_id,)
        )}
        set_tags(conn, mol_id, current_tags | set(tags))
    _recalculate_search_text(conn, mol_id)
    return mol_id, created


def get_molecule(conn: sqlite3.Connection, molecule_id: str) -> Json | None:
    row = conn.execute("SELECT * FROM molecules WHERE id = ?", (molecule_id,)).fetchone()
    if row is None:
        return None
    data = _row_to_molecule(row)
    for key, sql in {
        "files": "SELECT * FROM molecule_files WHERE molecule_id = ? ORDER BY kind, is_primary DESC",
        "aliases": "SELECT alias FROM molecule_aliases WHERE molecule_id = ? ORDER BY alias",
        "tags": "SELECT tag FROM molecule_tags WHERE molecule_id = ? ORDER BY tag",
        "sources": "SELECT source, source_id, url, license FROM molecule_sources WHERE molecule_id = ?",
        "studies": """SELECT s.id, s.name, s.pdb_id, sm.role, sm.is_primary
                      FROM studies s JOIN study_members sm ON sm.study_id = s.id
                      WHERE sm.molecule_id = ? ORDER BY s.name""",
        "collections": """SELECT c.id, c.name, c.parent_id
                          FROM collections c JOIN collection_members cm ON cm.collection_id = c.id
                          WHERE cm.molecule_id = ? ORDER BY c.name""",
    }.items():
        data[key] = [dict(item) for item in conn.execute(sql, (molecule_id,))]
    data["aliases"] = [item["alias"] for item in data["aliases"]]
    data["tags"] = [item["tag"] for item in data["tags"]]
    return data


def update_molecule(conn: sqlite3.Connection, molecule_id: str, patch: Json) -> bool:
    allowed = {
        "name", "kind_hint", "source", "source_id", "status", "prep_status",
        "canonical_smiles", "formula", "molecular_weight", "qed", "lipinski_violations",
    }
    updates = {key: value for key, value in patch.items() if key in allowed}
    if "metadata" in patch:
        current = conn.execute(
            "SELECT metadata_json FROM molecules WHERE id = ?", (molecule_id,)
        ).fetchone()
        if current is None:
            return False
        merged = json.loads(current["metadata_json"] or "{}")
        merged.update(patch["metadata"] or {})
        updates["metadata_json"] = _json(merged)
    if not updates:
        return get_molecule(conn, molecule_id) is not None
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE molecules SET {assignments} WHERE id = ?",
        (*updates.values(), molecule_id),
    )
    _recalculate_search_text(conn, molecule_id)
    return True


def delete_molecule(conn: sqlite3.Connection, molecule_id: str) -> bool:
    cursor = conn.execute("DELETE FROM molecules WHERE id = ?", (molecule_id,))
    return cursor.rowcount > 0


def create_collection(
    conn: sqlite3.Connection,
    *,
    name: str,
    parent_id: str | None = None,
    description: str = "",
    color: str | None = None,
    kind: str = "manual",
    query: Json | None = None,
) -> str:
    collection_id = new_id("col")
    now = _now()
    conn.execute(
        """INSERT INTO collections
           (id, parent_id, name, description, color, sort_order, kind, query_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
        (collection_id, parent_id, name.strip() or "untitled", description, color, kind, _json(query), now, now),
    )
    return collection_id


def add_collection_member(conn: sqlite3.Connection, collection_id: str, molecule_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO collection_members(collection_id, molecule_id) VALUES (?, ?)",
        (collection_id, molecule_id),
    )
    _recalculate_search_text(conn, molecule_id)


def remove_collection_member(conn: sqlite3.Connection, collection_id: str, molecule_id: str) -> None:
    conn.execute(
        "DELETE FROM collection_members WHERE collection_id = ? AND molecule_id = ?",
        (collection_id, molecule_id),
    )
    _recalculate_search_text(conn, molecule_id)


def create_study(
    conn: sqlite3.Connection,
    *,
    name: str,
    description: str = "",
    source: str = "",
    pdb_id: str | None = None,
) -> str:
    study_id = new_id("study")
    now = _now()
    conn.execute(
        """INSERT INTO studies(id, name, description, source, pdb_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (study_id, name.strip() or "untitled", description, source, pdb_id, now, now),
    )
    return study_id


def add_study_member(
    conn: sqlite3.Connection,
    study_id: str,
    molecule_id: str,
    *,
    role: str,
    is_primary: bool = False,
    sort_order: int = 0,
) -> None:
    conn.execute(
        """INSERT INTO study_members(study_id, molecule_id, role, is_primary, sort_order)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(study_id, molecule_id, role) DO UPDATE SET
             is_primary = MAX(study_members.is_primary, excluded.is_primary),
             sort_order = excluded.sort_order""",
        (study_id, molecule_id, role, int(is_primary), sort_order),
    )
    _recalculate_search_text(conn, molecule_id)


def remove_study_member(conn: sqlite3.Connection, study_id: str, molecule_id: str, role: str) -> None:
    conn.execute(
        "DELETE FROM study_members WHERE study_id = ? AND molecule_id = ? AND role = ?",
        (study_id, molecule_id, role),
    )
    _recalculate_search_text(conn, molecule_id)


def create_library(
    conn: sqlite3.Connection,
    *,
    name: str,
    description: str = "",
    source: str = "",
) -> str:
    library_id = new_id("lib")
    now = _now()
    conn.execute(
        """INSERT INTO libraries(id, name, description, source, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (library_id, name.strip() or "untitled", description, source, now, now),
    )
    return library_id


def add_library_member(
    conn: sqlite3.Connection,
    library_id: str,
    molecule_id: str,
    *,
    entry_index: int,
    prepared_path: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO library_members
           (library_id, molecule_id, entry_index, prepared_path, added_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(library_id, molecule_id) DO UPDATE SET
             entry_index = excluded.entry_index,
             prepared_path = COALESCE(excluded.prepared_path, library_members.prepared_path)""",
        (library_id, molecule_id, entry_index, prepared_path, _now()),
    )


def summary(conn: sqlite3.Connection) -> Json:
    def count(table: str) -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    return {
        "molecules": count("molecules"),
        "studies": count("studies"),
        "collections": count("collections"),
        "libraries": count("libraries"),
    }


def list_collections(conn: sqlite3.Connection) -> list[Json]:
    rows = conn.execute(
        """SELECT c.*, COUNT(cm.molecule_id) AS molecule_count
           FROM collections c LEFT JOIN collection_members cm ON cm.collection_id = c.id
           GROUP BY c.id ORDER BY c.sort_order, c.name COLLATE NOCASE"""
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["query"] = json.loads(item.pop("query_json", "{}") or "{}")
        result.append(item)
    return result


def update_collection(conn: sqlite3.Connection, collection_id: str, patch: Json) -> bool:
    allowed = {"name", "description", "color", "parent_id", "sort_order", "kind", "query"}
    updates = {}
    for key, value in patch.items():
        if key == "query":
            updates["query_json"] = _json(value)
        elif key in allowed:
            updates[key] = value
    if not updates:
        return False
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    cursor = conn.execute(
        f"UPDATE collections SET {assignments} WHERE id = ?",
        (*updates.values(), collection_id),
    )
    return cursor.rowcount > 0


def delete_collection(conn: sqlite3.Connection, collection_id: str) -> bool:
    cursor = conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    return cursor.rowcount > 0


def list_studies(conn: sqlite3.Connection) -> list[Json]:
    rows = conn.execute(
        """SELECT s.*,
                  SUM(CASE WHEN sm.role = 'receptor' THEN 1 ELSE 0 END) AS receptor_count,
                  SUM(CASE WHEN sm.role = 'ligand' THEN 1 ELSE 0 END) AS ligand_count
           FROM studies s LEFT JOIN study_members sm ON sm.study_id = s.id
           GROUP BY s.id ORDER BY s.name COLLATE NOCASE"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_study(conn: sqlite3.Connection, study_id: str) -> Json | None:
    study = conn.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
    if study is None:
        return None
    data = dict(study)
    members = conn.execute(
        """SELECT sm.role, sm.is_primary, sm.sort_order,
                  m.id, m.name, m.kind_hint, m.prep_status, m.canonical_smiles
           FROM study_members sm JOIN molecules m ON m.id = sm.molecule_id
           WHERE sm.study_id = ? ORDER BY sm.role, sm.sort_order, m.name""",
        (study_id,),
    ).fetchall()
    data["members"] = [dict(row) for row in members]
    data["receptors"] = [item for item in data["members"] if item["role"] == "receptor"]
    data["ligands"] = [item for item in data["members"] if item["role"] == "ligand"]
    data["receptor_count"] = len(data["receptors"])
    data["ligand_count"] = len(data["ligands"])
    return data


def update_study(conn: sqlite3.Connection, study_id: str, patch: Json) -> bool:
    allowed = {"name", "description", "source", "pdb_id"}
    updates = {key: value for key, value in patch.items() if key in allowed}
    if not updates:
        return False
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    cursor = conn.execute(
        f"UPDATE studies SET {assignments} WHERE id = ?", (*updates.values(), study_id)
    )
    return cursor.rowcount > 0


def delete_study(conn: sqlite3.Connection, study_id: str) -> bool:
    cursor = conn.execute("DELETE FROM studies WHERE id = ?", (study_id,))
    return cursor.rowcount > 0


def list_libraries(conn: sqlite3.Connection) -> list[Json]:
    rows = conn.execute(
        """SELECT l.*, COUNT(lm.molecule_id) AS molecule_count,
                  SUM(CASE WHEN lm.prepared_path IS NOT NULL THEN 1 ELSE 0 END) AS prepared_count
           FROM libraries l LEFT JOIN library_members lm ON lm.library_id = l.id
           GROUP BY l.id ORDER BY l.updated_at DESC, l.name COLLATE NOCASE"""
    ).fetchall()
    return [dict(row) for row in rows]


def get_library(conn: sqlite3.Connection, library_id: str) -> Json | None:
    library = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
    if library is None:
        return None
    data = dict(library)
    data["members"] = [
        dict(row)
        for row in conn.execute(
            """SELECT lm.entry_index, lm.prepared_path, m.id, m.name, m.kind_hint,
                      m.prep_status, m.canonical_smiles
               FROM library_members lm JOIN molecules m ON m.id = lm.molecule_id
               WHERE lm.library_id = ? ORDER BY lm.entry_index""",
            (library_id,),
        )
    ]
    data["molecule_count"] = len(data["members"])
    data["prepared_count"] = sum(
        1 for item in data["members"] if item["prepared_path"] is not None
    )
    return data


def update_library(conn: sqlite3.Connection, library_id: str, patch: Json) -> bool:
    allowed = {"name", "description", "source"}
    updates = {key: value for key, value in patch.items() if key in allowed}
    if not updates:
        return False
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    cursor = conn.execute(
        f"UPDATE libraries SET {assignments} WHERE id = ?", (*updates.values(), library_id)
    )
    return cursor.rowcount > 0


def delete_library(conn: sqlite3.Connection, library_id: str) -> bool:
    cursor = conn.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
    return cursor.rowcount > 0


def list_saved_views(conn: sqlite3.Connection, scope: str = "molecules") -> list[Json]:
    rows = conn.execute(
        "SELECT * FROM saved_views WHERE scope = ? ORDER BY updated_at DESC, name",
        (scope,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "query": json.loads(row["query_json"] or "{}"),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def create_saved_view(
    conn: sqlite3.Connection, *, name: str, query: Json, scope: str = "molecules"
) -> Json:
    view_id = new_id("view")
    now = _now()
    conn.execute(
        """INSERT INTO saved_views(id, name, scope, query_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             query_json = excluded.query_json,
             scope = excluded.scope,
             updated_at = excluded.updated_at""",
        (view_id, name.strip() or "view", scope, _json(query), now, now),
    )
    row = conn.execute("SELECT * FROM saved_views WHERE name = ?", (name.strip(),)).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "scope": row["scope"],
        "query": json.loads(row["query_json"] or "{}"),
        "createdAt": row["created_at"],
    }


def delete_saved_view(conn: sqlite3.Connection, view_id: str) -> bool:
    cursor = conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
    return cursor.rowcount > 0


def get_collection(conn: sqlite3.Connection, collection_id: str) -> Json | None:
    row = conn.execute("SELECT * FROM collections WHERE id = ?", (collection_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["query"] = json.loads(data.pop("query_json", "{}") or "{}")
    data["members"] = [
        dict(item)
        for item in conn.execute(
            """SELECT m.id, m.name, m.kind_hint, m.prep_status
               FROM collection_members cm JOIN molecules m ON m.id = cm.molecule_id
               WHERE cm.collection_id = ? ORDER BY m.name""",
            (collection_id,),
        )
    ]
    data["molecule_count"] = len(data["members"])
    return data


def set_primary_receptor(conn: sqlite3.Connection, study_id: str, molecule_id: str) -> bool:
    row = conn.execute(
        "SELECT role FROM study_members WHERE study_id = ? AND molecule_id = ?",
        (study_id, molecule_id),
    ).fetchone()
    if row is None or row["role"] != "receptor":
        return False
    conn.execute(
        "UPDATE study_members SET is_primary = CASE WHEN molecule_id = ? THEN 1 ELSE 0 END "
        "WHERE study_id = ? AND role = 'receptor'",
        (molecule_id, study_id),
    )
    conn.execute("UPDATE studies SET updated_at = ? WHERE id = ?", (_now(), study_id))
    return True


def bulk_add_tags(conn: sqlite3.Connection, molecule_ids: Iterable[str], tags: Iterable[str]) -> int:
    values = [tag.strip() for tag in tags if tag.strip()]
    if not values:
        return 0
    changed = 0
    for molecule_id in molecule_ids:
        for tag in values:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO molecule_tags(molecule_id, tag) VALUES (?, ?)",
                (molecule_id, tag),
            )
            if cursor.rowcount:
                changed += 1
        _recalculate_search_text(conn, molecule_id)
    return changed
