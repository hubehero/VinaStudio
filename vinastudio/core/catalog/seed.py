"""The optional built-in undergraduate drug library.

The data is a versioned CSV shipped with the application.  Seeding happens
once per workspace and is deliberately not a protected resource: the resulting
molecules, collection and Library are ordinary Catalog objects, so a user can
edit or delete them.  A deleted Library is not recreated on the next launch.
"""

from __future__ import annotations

import csv
import logging
import os
import shutil
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from vinastudio.config import RESOURCES_DIR
from vinastudio.core.catalog import store
from vinastudio.core.catalog.identity import Identity, identity_from_smiles
from vinastudio.core.catalog.library import materialize_library
from vinastudio.core.chem.pdb_stats import polymer_molecular_weight
from vinastudio.core.paths import slugify

log = logging.getLogger(__name__)

SEED_VERSION = "1"
MARKER = "builtin_undergrad_drugs_v1"
DATA_FILE = RESOURCES_DIR / "catalog" / "undergraduate_drugs.csv"
RECEPTOR_DATA_FILE = RESOURCES_DIR / "catalog" / "undergraduate_receptors.csv"
RECEPTOR_PDB_DIR = RESOURCES_DIR / "catalog" / "receptors"
LIBRARY_NAME = "本科药物化学常用药物（内置）"
COLLECTION_NAME = "本科药物化学"
RECEPTOR_COLLECTION_NAME = "本科药物靶点"
RECEPTOR_MARKER = "builtin_undergrad_receptors_v1"
SEED_ENV = "VINASTUDIO_BUILTIN_LIBRARY_SEED"

LIBRARY_DESCRIPTION = (
    "本科药理学/药物化学常用小分子药物，按药物类别整理。"
    "仅用于教学与分子建模练习，不包含剂量或临床用药建议；"
    "结构来自 PubChem，导入后可按需准备 3D/PDBQT。"
)


def seed_enabled() -> bool:
    value = os.environ.get(SEED_ENV, "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _rows() -> list[dict[str, str]]:
    try:
        with DATA_FILE.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("smiles")]
    except OSError:
        log.warning("built-in Catalog data is unavailable: %s", DATA_FILE)
        return []


def _write_2d_sdf(smiles: str, target: Path, name: str) -> bool:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    AllChem.Compute2DCoords(mol)
    mol.SetProp("_Name", name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(Chem.MolToMolBlock(mol) + "$$$$\n", encoding="utf-8")
    return True


def _ensure_collection(conn, name: str, parent_id: str | None = None) -> str:
    rows = conn.execute(
        "SELECT id, parent_id FROM collections WHERE name = ?", (name,)
    ).fetchall()
    for row in rows:
        if row["parent_id"] == parent_id:
            return str(row["id"])
    return store.create_collection(conn, name=name, parent_id=parent_id)


def _ensure_library(conn) -> str:
    row = conn.execute(
        "SELECT id FROM libraries WHERE source = 'builtin' AND name = ? LIMIT 1",
        (LIBRARY_NAME,),
    ).fetchone()
    if row:
        return str(row["id"])
    return store.create_library(
        conn,
        name=LIBRARY_NAME,
        description=LIBRARY_DESCRIPTION,
        source="builtin",
    )


def _backfill_receptor_weights(conn) -> int:
    rows = conn.execute(
        """
        SELECT m.id, f.path
        FROM molecules m
        JOIN molecule_files f ON f.molecule_id = m.id AND f.is_primary = 1
        WHERE m.kind_hint = 'receptor' AND m.molecular_weight IS NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        weight = polymer_molecular_weight(row["path"])
        if weight is not None:
            store.set_molecular_weight(conn, str(row["id"]), weight)
            updated += 1
    if updated:
        log.info("backfilled polymer mass for %d receptor(s)", updated)
    return updated


def seed_builtin_receptors(conn, workspace: Path) -> int:
    """Seed the offline undergraduate drug-target collection once.

    Receptors are ordinary Catalog molecules in a Collection (not a screening
    Library): a Library is a ligand input and must not be selectable as a
    screening ligand set. The raw RCSB PDB files are copied into the workspace
    so preview/preparation stay offline after installation.
    """
    marker = conn.execute(
        "SELECT value FROM catalog_meta WHERE key = ?", (RECEPTOR_MARKER,)
    ).fetchone()
    if marker is not None:
        _backfill_receptor_weights(conn)
        return 0
    try:
        with RECEPTOR_DATA_FILE.open(newline="", encoding="utf-8") as handle:
            rows = [row for row in csv.DictReader(handle) if row.get("pdb_id")]
    except OSError:
        log.warning("built-in receptor data is unavailable: %s", RECEPTOR_DATA_FILE)
        return 0
    source_dir = workspace / "receptors" / "builtin"
    source_dir.mkdir(parents=True, exist_ok=True)
    parent_id = _ensure_collection(conn, RECEPTOR_COLLECTION_NAME)
    group_collections: dict[str, str] = {}
    added = 0
    for row in rows:
        pdb_id = row["pdb_id"].strip().upper()
        source = RECEPTOR_PDB_DIR / f"{pdb_id}.pdb"
        if not source.is_file():
            log.warning("built-in receptor structure is missing: %s", source)
            continue
        target = source_dir / f"{pdb_id}.pdb"
        if not target.is_file():
            shutil.copy2(source, target)
        molecule_id, _ = store.upsert_molecule(
            conn,
            name=row["target"].strip() or pdb_id,
            identity=Identity(key=f"pdb:{pdb_id}", kind="pdb"),
            kind_hint="receptor",
            source="RCSB PDB",
            source_id=pdb_id,
            source_url=f"https://www.rcsb.org/structure/{pdb_id}",
            license="RCSB PDB",
            metadata={
                "builtin": True,
                "pdbId": pdb_id,
                "gene": row.get("gene", ""),
                "targetClass": row.get("target_class", ""),
                "classZh": row.get("class_zh", ""),
                "organism": row.get("organism", ""),
                "chain": row.get("chain", ""),
                "ligand": row.get("ligand", ""),
                "resolution": row.get("resolution", ""),
                "method": row.get("method", ""),
                "note": row.get("note", ""),
                "teachingOnly": True,
            },
            files=[{
                "kind": "source",
                "path": str(target),
                "path_kind": "workspace",
                "is_primary": True,
            }],
            aliases=[row.get("target_zh", "").strip()],
            tags=[
                "builtin",
                "undergraduate",
                f"target_class:{row.get('target_class', '').strip()}",
                row.get("class_zh", "").strip(),
            ],
        )
        weight = polymer_molecular_weight(target)
        if weight is not None:
            store.set_molecular_weight(conn, molecule_id, weight)
        store.add_collection_member(conn, parent_id, molecule_id)
        group_key = row.get("target_class", "").strip() or "other"
        group_id = group_collections.get(group_key)
        if group_id is None:
            group_id = _ensure_collection(
                conn, row.get("class_zh", "").strip() or "其他", parent_id
            )
            group_collections[group_key] = group_id
        store.add_collection_member(conn, group_id, molecule_id)
        added += 1
    conn.execute(
        "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES (?, '1')",
        (RECEPTOR_MARKER,),
    )
    log.info("seeded built-in receptor collection: %d structure(s)", added)
    return added


def seed_builtin_library(conn, workspace: Path) -> int:
    """Seed the versioned library once; returns the number of molecules added.

    The marker is written after a successful attempt, so a deleted library is
    intentionally not restored by a later launch.  Existing identities are
    merged by the normal Catalog rules, which makes a retry after an interrupted
    first attempt safe.
    """
    marker = conn.execute(
        "SELECT value FROM catalog_meta WHERE key = ?", (MARKER,)
    ).fetchone()
    if marker is not None:
        return 0
    rows = _rows()
    if not rows:
        return 0

    source_dir = workspace / "ligands" / "builtin"
    source_dir.mkdir(parents=True, exist_ok=True)
    collection_id = _ensure_collection(conn, COLLECTION_NAME)
    group_collections: dict[str, str] = {}
    library_id = _ensure_library(conn)
    next_index = int(
        conn.execute(
            "SELECT COALESCE(MAX(entry_index) + 1, 0) FROM library_members WHERE library_id = ?",
            (library_id,),
        ).fetchone()[0]
    )
    added = 0
    for row in rows:
        name = row["name"].strip()
        smiles = row["smiles"].strip()
        cid = row["cid"].strip()
        target = source_dir / f"{int(cid):08d}-{slugify(name)}.sdf"
        if not _write_2d_sdf(smiles, target, name):
            log.warning("built-in drug %s has an unparseable SMILES", name)
            continue
        identity = identity_from_smiles(smiles)
        if identity is None:
            continue
        class_name = row["drug_class"].strip()
        class_zh = row["class_zh"].strip()
        aliases = [value for value in (row["zh_name"].strip(),) if value]
        aliases += [
            value.strip()
            for value in (row.get("aliases") or "").split(";")
            if value.strip()
        ]
        tags = ["builtin", "undergraduate", f"class:{class_name}"]
        if class_zh:
            tags.append(class_zh)
        molecule_id, _ = store.upsert_molecule(
            conn,
            name=name,
            identity=identity,
            kind_hint="ligand",
            source="PubChem",
            source_id=cid,
            source_url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
            license="PubChem",
            metadata={
                "builtin": True,
                "builtinVersion": SEED_VERSION,
                "drugClass": class_name,
                "classZh": class_zh,
                "pubchemCid": cid,
                "teachingOnly": True,
            },
            files=[{
                "kind": "source",
                "path": str(target),
                "path_kind": "workspace",
                "is_primary": True,
            }],
            aliases=aliases,
            tags=tags,
        )
        store.add_collection_member(conn, collection_id, molecule_id)
        group_key = row["group"].strip() or "other"
        group_id = group_collections.get(group_key)
        if group_id is None:
            group_id = _ensure_collection(
                conn, row["group_zh"].strip() or "其他", collection_id
            )
            group_collections[group_key] = group_id
        store.add_collection_member(conn, group_id, molecule_id)
        existing = conn.execute(
            "SELECT 1 FROM library_members WHERE library_id = ? AND molecule_id = ?",
            (library_id, molecule_id),
        ).fetchone()
        if existing is None:
            store.add_library_member(
                conn,
                library_id,
                molecule_id,
                entry_index=next_index,
            )
            next_index += 1
            added += 1
    materialize_library(conn, library_id, workspace=workspace)
    conn.execute(
        "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES (?, ?)",
        (MARKER, SEED_VERSION),
    )
    log.info("seeded built-in undergraduate library: %d molecule(s)", added)
    return added
