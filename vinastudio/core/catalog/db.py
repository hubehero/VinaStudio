"""Workspace catalog database: schema, connections and migrations.

The catalog is the durable index for molecules, their files, Study/Collection
membership and screening libraries. It deliberately stores no structures or
pose bytes: structures stay on disk, and the catalog stores identity,
metadata and relative paths.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from vinastudio.core import paths

SCHEMA_VERSION = 1

_WRITE_LOCK = threading.RLock()


class CatalogError(RuntimeError):
    """The catalog exists but cannot be used (corrupt or too new)."""


def catalog_path() -> Path:
    """``<workspace>/catalog.sqlite`` for both workspace layouts.

    ``workspace_root()`` is ``<workspace>/jobs`` when a workspace is active
    and ``<app_home>/workspace`` otherwise; the catalog sits beside it, just
    like the results index.
    """
    root = paths.workspace_root()
    parent = root.parent if root.name == "jobs" else root
    return parent / "catalog.sqlite"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open one catalog connection; callers close it."""
    target = db_path or catalog_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def transaction(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Serialise a write transaction and roll back on any exception."""
    with _WRITE_LOCK:
        conn = connect(db_path)
        try:
            ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


_TABLE_DDL = (
    """CREATE TABLE IF NOT EXISTS molecules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind_hint TEXT NOT NULL DEFAULT 'unknown',
        source TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL DEFAULT '',
        identity_key TEXT NOT NULL,
        identity_kind TEXT NOT NULL,
        canonical_smiles TEXT,
        inchi_key TEXT,
        parent_inchi_key TEXT,
        formula TEXT,
        molecular_weight REAL,
        qed REAL,
        lipinski_violations INTEGER,
        status TEXT NOT NULL DEFAULT 'active',
        prep_status TEXT NOT NULL DEFAULT 'unknown',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        search_text TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        UNIQUE(identity_key)
    )""",
    """CREATE TABLE IF NOT EXISTS molecule_files (
        id TEXT PRIMARY KEY,
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        path TEXT NOT NULL,
        path_kind TEXT NOT NULL DEFAULT 'workspace',
        sha256 TEXT,
        bytes INTEGER NOT NULL DEFAULT 0,
        mtime REAL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        UNIQUE(molecule_id, path, kind)
    )""",
    """CREATE TABLE IF NOT EXISTS molecule_aliases (
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        alias TEXT NOT NULL,
        locale TEXT,
        PRIMARY KEY (molecule_id, alias)
    )""",
    """CREATE TABLE IF NOT EXISTS molecule_tags (
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        PRIMARY KEY (molecule_id, tag)
    )""",
    """CREATE TABLE IF NOT EXISTS molecule_sources (
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL DEFAULT '',
        url TEXT,
        license TEXT,
        PRIMARY KEY (molecule_id, source, source_id)
    )""",
    """CREATE TABLE IF NOT EXISTS collections (
        id TEXT PRIMARY KEY,
        parent_id TEXT REFERENCES collections(id) ON DELETE SET NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        color TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        kind TEXT NOT NULL DEFAULT 'manual',
        query_json TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS collection_members (
        collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        PRIMARY KEY (collection_id, molecule_id)
    )""",
    """CREATE TABLE IF NOT EXISTS studies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        pdb_id TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS study_members (
        study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        sort_order INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (study_id, molecule_id, role)
    )""",
    """CREATE TABLE IF NOT EXISTS libraries (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS library_members (
        library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
        molecule_id TEXT NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
        entry_index INTEGER NOT NULL,
        prepared_path TEXT,
        added_at REAL NOT NULL,
        PRIMARY KEY (library_id, molecule_id),
        UNIQUE (library_id, entry_index)
    )""",
    """CREATE TABLE IF NOT EXISTS saved_views (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL,
        query_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS catalog_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_molecules_identity
        ON molecules(identity_key)""",
    """CREATE INDEX IF NOT EXISTS idx_molecules_kind ON molecules(kind_hint)""",
    """CREATE INDEX IF NOT EXISTS idx_molecules_status ON molecules(status)""",
    """CREATE INDEX IF NOT EXISTS idx_molecules_updated ON molecules(updated_at)""",
    """CREATE INDEX IF NOT EXISTS idx_molecule_files_molecule
        ON molecule_files(molecule_id)""",
    """CREATE INDEX IF NOT EXISTS idx_study_members_molecule
        ON study_members(molecule_id)""",
    """CREATE INDEX IF NOT EXISTS idx_study_members_study
        ON study_members(study_id)""",
    """CREATE INDEX IF NOT EXISTS idx_collection_members_molecule
        ON collection_members(molecule_id)""",
    """CREATE INDEX IF NOT EXISTS idx_library_members_library
        ON library_members(library_id, entry_index)""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS molecule_fts USING fts5(
        name,
        search_text,
        content='molecules',
        content_rowid='rowid',
        tokenize='unicode61'
    )""",
    """CREATE TRIGGER IF NOT EXISTS molecules_fts_ai AFTER INSERT ON molecules BEGIN
        INSERT INTO molecule_fts(rowid, name, search_text)
        VALUES (new.rowid, new.name, new.search_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS molecules_fts_ad AFTER DELETE ON molecules BEGIN
        INSERT INTO molecule_fts(molecule_fts, rowid, name, search_text)
        VALUES ('delete', old.rowid, old.name, old.search_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS molecules_fts_au AFTER UPDATE ON molecules BEGIN
        INSERT INTO molecule_fts(molecule_fts, rowid, name, search_text)
        VALUES ('delete', old.rowid, old.name, old.search_text);
        INSERT INTO molecule_fts(rowid, name, search_text)
        VALUES (new.rowid, new.name, new.search_text);
    END""",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create or migrate the catalog; refuse a newer schema."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    version = int(row["version"]) if row is not None else 0
    if version > SCHEMA_VERSION:
        raise CatalogError(
            f"catalog schema v{version} is newer than supported v{SCHEMA_VERSION}"
        )
    for ddl in _TABLE_DDL:
        conn.execute(ddl)
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    elif version < SCHEMA_VERSION:
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    conn.commit()
