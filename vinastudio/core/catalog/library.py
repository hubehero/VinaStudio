"""Materialise a catalog Library into the screening worker's on-disk layout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

from rdkit import Chem

from vinastudio.core.catalog import store
from vinastudio.core.chem.library import MOLS_DIRNAME, libraries_root
from vinastudio.core.chem.rdkit_io import mol_from_file
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import resolve_within


def _write_sdf(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix == ".sdf":
        shutil.copyfile(source, target)
        return
    mol = mol_from_file(source, sanitize=True, removeHs=False)
    if mol is None:
        raise InvalidInputError(f"cannot convert {source.name} to an SDF record")
    target.write_text(Chem.MolToMolBlock(mol) + "$$$$\n", encoding="utf-8")


def _source_sdf(conn: sqlite3.Connection, molecule_id: str) -> Path | None:
    detail = store.get_molecule(conn, molecule_id)
    if detail is None:
        return None
    for item in detail["files"]:
        path = Path(item["path"])
        if path.suffix.lower() in {".sdf", ".mol", ".mol2", ".pdb"} and path.is_file():
            return path
    return None


def invalidate_library_materialization(workspace: Path, library_id: str) -> None:
    """Remove a derived legacy-layout copy after a membership change.

    The Catalog view is authoritative; the ``libraries/<id>`` directory is a
    legacy screening view. Leaving the old copy in place made the two views
    disagree after a member deletion.
    """
    try:
        destination = resolve_within(libraries_root(workspace / "libraries"), library_id)
    except ValueError:
        return
    if destination.is_dir():
        shutil.rmtree(destination, ignore_errors=True)


def materialize_library(
    conn: sqlite3.Connection,
    library_id: str,
    *,
    workspace: Path,
) -> Path:
    """Write ``libraries/<id>/index.json`` and one SDF per member.

    The screening worker predates the catalog and consumes this layout; keeping
    that contract means a catalog Library can be screened without a parallel
    worker implementation.
    """
    library = store.get_library(conn, library_id)
    if library is None:
        raise InvalidInputError(f"library not found: {library_id}")
    root = libraries_root(workspace / "libraries")
    try:
        destination = resolve_within(root, library_id)
    except ValueError as exc:
        raise InvalidInputError(f"invalid library id: {library_id}") from exc
    members = store.library_entries(conn, library_id)
    signature = hashlib.sha256(
        json.dumps(
            [
                {
                    "index": int(member.get("entry_index", 0)),
                    "id": member.get("id"),
                    "prepared": member.get("prepared_path"),
                }
                for member in members
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    index_path = destination / "index.json"
    try:
        existing = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    if existing.get("materializedSignature") == signature:
        return destination

    mols = destination / MOLS_DIRNAME
    mols.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    used = 0
    for member in members:
        source_value = member.get("source_path")
        source = Path(str(source_value)) if source_value else None
        if source is None or not source.is_file():
            raise InvalidInputError(
                f"molecule {member['name']} has no renderable SDF source; "
                "prepare/export it before adding it to a screening library"
            )
        index = int(member["entry_index"])
        target = mols / f"{index:06d}.sdf"
        _write_sdf(source, target)
        prepared = member.get("prepared_path")
        if prepared:
            try:
                prepared_path = resolve_within(workspace, str(prepared))
            except ValueError:
                prepared_path = None
            if prepared_path is not None and prepared_path.is_file():
                shutil.copyfile(prepared_path, mols / f"{index:06d}.pdbqt")
        entries.append({
            "index": index,
            "name": member["name"],
            "file": f"{MOLS_DIRNAME}/{index:06d}.sdf",
            "prepare": "none",
            "molWt": None,
            "qed": None,
            "lipinskiViolations": None,
        })
        used += 1
    payload = {
        "schemaVersion": 1,
        "name": library_id,
        "displayName": library.get("name") or library_id,
        "created": store._now(),
        "entries": entries,
        "materializedSignature": signature,
    }
    tmp = destination / "index.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, index_path)
    if used == 0:
        raise InvalidInputError(f"library {library_id} has no ligands to materialise")
    return destination
