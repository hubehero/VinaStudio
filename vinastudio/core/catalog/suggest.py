"""Explainable, local-only classification suggestions.

No model and no network: every suggestion names the rule that produced it and
carries a confidence. Applying a suggestion is always an explicit user action.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Any

_PDB = re.compile(r"(?:^|[_\-\s])([0-9][A-Za-z0-9]{3})(?:[_\-\s]|$)")


def _suggestion(
    kind: str,
    title: str,
    reason: str,
    confidence: float,
    molecule_ids: list[str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{kind}:{'-'.join(sorted(molecule_ids))}",
        "kind": kind,
        "title": title,
        "reason": reason,
        "confidence": round(confidence, 3),
        "moleculeIds": molecule_ids,
        "payload": payload or {},
    }


def build_suggestions(conn: sqlite3.Connection, *, limit: int = 30) -> list[dict[str, Any]]:
    """Return deterministic suggestions for unassigned/messy catalog rows."""
    suggestions: list[dict[str, Any]] = []

    # 1. Pair receptor + ligand by a visible PDB-style filename prefix.
    rows = conn.execute(
        """SELECT m.id, m.name, m.kind_hint, m.source, m.inchi_key, m.parent_inchi_key
           FROM molecules m
           WHERE NOT EXISTS (SELECT 1 FROM study_members sm WHERE sm.molecule_id = m.id)
           ORDER BY m.name"""
    ).fetchall()
    by_pdb: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        match = _PDB.search(row["name"].lower())
        if match:
            by_pdb[match.group(1).upper()].append(row)
    for pdb_id, members in sorted(by_pdb.items()):
        receptors = [m for m in members if m["kind_hint"] == "receptor"]
        ligands = [m for m in members if m["kind_hint"] == "ligand"]
        if receptors and ligands:
            ids = [m["id"] for m in receptors + ligands]
            suggestions.append(_suggestion(
                "study_pairs",
                f"Create a study for {pdb_id}",
                f"{len(receptors)} receptor(s) and {len(ligands)} ligand(s) share the "
                f"filename/source prefix {pdb_id}; pairing does not imply a validated complex.",
                0.88,
                ids,
                {"pdbId": pdb_id, "receptorCount": len(receptors), "ligandCount": len(ligands)},
            ))

    # 2. Unknown role: the detector was not able to decide.
    unknown = conn.execute(
        "SELECT id, name FROM molecules WHERE kind_hint = 'unknown' ORDER BY name LIMIT 10"
    ).fetchall()
    for row in unknown:
        suggestions.append(_suggestion(
            "role",
            f"Classify {row['name']}",
            "The file could not be classified from extension/content; choose receptor or ligand.",
            0.5,
            [row["id"]],
        ))

    # 3. Parent-key duplicates: same scaffold/salt family, not automatically merged.
    groups = defaultdict(list)
    for row in conn.execute(
        "SELECT id, name, parent_inchi_key FROM molecules WHERE parent_inchi_key IS NOT NULL"
    ):
        groups[row["parent_inchi_key"]].append(row)
    for parent, members in groups.items():
        if len(members) > 1:
            suggestions.append(_suggestion(
                "duplicates",
                f"Review {len(members)} possible duplicates",
                "Structures share a parent InChIKey; salts/stereo variants may be distinct. "
                "Review before merging files or metadata.",
                0.72,
                [m["id"] for m in members],
                {"parentInchiKey": parent},
            ))

    # 4. No prepared artifact: batch/screening needs 3D PDBQT.
    for row in conn.execute(
        """SELECT m.id, m.name FROM molecules m
           WHERE m.kind_hint = 'ligand'
             AND NOT EXISTS (SELECT 1 FROM molecule_files f
                             WHERE f.molecule_id = m.id AND f.kind = 'pdbqt')
             AND NOT EXISTS (SELECT 1 FROM library_members lm WHERE lm.molecule_id = m.id)
           LIMIT 10"""
    ):
        suggestions.append(_suggestion(
            "prepare",
            f"Prepare {row['name']} before screening",
            "No PDBQT artifact is recorded; a 2D/SDF molecule must be prepared for docking.",
            0.9,
            [row["id"]],
        ))

    suggestions.sort(key=lambda item: (-item["confidence"], item["kind"], item["id"]))
    return suggestions[:limit]
