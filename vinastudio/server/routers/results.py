"""Cross-project results search endpoints (TASK-15) and IFP grouping (TASK-16).

The search/compare endpoints treat the index as optional infrastructure: a
missing or corrupt ``results.sqlite`` degrades to an empty list plus a
server-side warning, never to a 500 (design §3 / task book §6.3).  The
IFP-grouping endpoint does not read the index at all — it fingerprints the
ligand files the request names, inside the active workspace.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from vinastudio.core import results_db
from vinastudio.core.chem.ifp import (
    CONTACT_TYPES,
    butina_clustering,
    fingerprint,
    parse_ligand_atoms,
    parse_receptor_atoms,
    residue_columns,
    tanimoto,
)
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import resolve_within
from vinastudio.schemas.docking import IfpClusterRow
from vinastudio.schemas.results import (
    IfpGroupLigandRow,
    IfpGroupRequest,
    IfpGroupResponse,
    ResultRunDetail,
    ResultRunSummary,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/results", tags=["results"])

_DEGRADED_ON = (sqlite3.Error, OSError, results_db.ResultsDbError)

#: Process-local FIFO cache for the grouping endpoint (task book P2-B):
#: identical receptor/ligand set + cutoff re-serve instantly until any file's
#: identity (path, size, mtime_ns) changes.  Four entries deep — the report
#: surface only ever needs the last few views, never history.
_IFP_CLUSTER_CACHE_MAXSIZE = 4
_ifp_cluster_cache: OrderedDict[tuple[Any, ...], IfpGroupResponse] = OrderedDict()
_ifp_cluster_cache_lock = threading.Lock()


@router.get("/search", response_model=list[ResultRunSummary])
def search_results(q: str = "", limit: int = results_db.DEFAULT_LIMIT) -> list[ResultRunSummary]:
    try:
        rows = results_db.search_runs(q, limit=limit)
    except _DEGRADED_ON as exc:
        log.warning("results search degraded: %s", exc, exc_info=True)
        return []
    return [ResultRunSummary(**row) for row in rows]


@router.get("/compare", response_model=list[ResultRunDetail])
def compare_results(runIds: str = "") -> list[ResultRunDetail]:
    """Comma-joined ids, request order kept, unknown ids silently skipped."""
    run_ids = [part.strip() for part in runIds.split(",") if part.strip()]
    try:
        rows = results_db.compare_runs(run_ids)
    except _DEGRADED_ON as exc:
        log.warning("results compare degraded: %s", exc, exc_info=True)
        return []
    return [ResultRunDetail(**row) for row in rows]


@router.post("/ifp-cluster", response_model=IfpGroupResponse)
def ifp_cluster_ligands(request: IfpGroupRequest) -> IfpGroupResponse:
    """BUTINA-group ligands by interaction fingerprint (report-only, cached).

    Every path must resolve inside the active workspace — the request body
    carries filesystem paths, so this is the path-traversal gate (task book
    勘误 ⑤) and it runs before the in-process cache is even consulted.
    Each ligand contributes its first PDBQT model / first SDF record only;
    ligands 2..200 are enforced by the schema.  Identical inputs re-serve
    from a small FIFO cache: fingerprinting is the expensive part and the
    files stay put until the user swaps them (task book P2-B).
    """
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    if ws is None:
        raise InvalidInputError("no workspace configured")

    receptor_path = _resolve_in_workspace(ws, request.receptorPath, "receptorPath")
    ligand_paths = [
        (_resolve_in_workspace(ws, ligand.pdbqtPath, "pdbqtPath"), ligand.label)
        for ligand in request.ligands
    ]
    # File identity + labels + cutoff: any of them changing means a different
    # response, so all of them ride in the key (labels are display data that
    # may change while the bytes stay identical).
    cache_key = (
        _file_identity(receptor_path),
        tuple((*_file_identity(path), label) for path, label in ligand_paths),
        request.cutoff,
    )
    with _ifp_cluster_cache_lock:
        cached = _ifp_cluster_cache.get(cache_key)
    if cached is not None:
        return cached

    receptor_atoms = parse_receptor_atoms(str(receptor_path))
    labels: list[str] = []
    bit_sets = []
    for path, label in ligand_paths:
        atoms = parse_ligand_atoms(path=str(path))
        labels.append(label)
        bit_sets.append(fingerprint(receptor_atoms, atoms))

    residues, index_of = residue_columns(receptor_atoms, bit_sets)
    # One tanimoto pass feeds both the clustering distances and the wire
    # matrix — the two loops used to each recompute the full N×N grid.
    sim = [[tanimoto(a, b) for b in bit_sets] for a in bit_sets]
    distances = [[1.0 - value for value in row] for row in sim]

    clusters: list[IfpClusterRow] = []
    cluster_of: dict[int, int] = {}
    for cluster_index, (members, centroid) in enumerate(
        butina_clustering(distances, request.cutoff)
    ):
        clusters.append(
            IfpClusterRow(members=members, centroid=centroid, size=len(members))
        )
        for member in members:
            cluster_of[member] = cluster_index

    ligand_rows = [
        IfpGroupLigandRow(
            index=index,
            label=labels[index],
            nContacts=len(bit_sets[index]),
            cluster=cluster_of.get(index, 0),
            pairs=sorted((index_of[key], order) for key, order in bit_sets[index]),
        )
        for index in range(len(bit_sets))
    ]

    response = IfpGroupResponse(
        residues=residues,
        types=list(CONTACT_TYPES),
        ligands=ligand_rows,
        clusters=clusters,
        nClusters=len(clusters),
        cutoff=request.cutoff,
        matrix=[[round(value, 3) for value in row] for row in sim],
    )
    with _ifp_cluster_cache_lock:
        while len(_ifp_cluster_cache) >= _IFP_CLUSTER_CACHE_MAXSIZE:
            _ifp_cluster_cache.popitem(last=False)
        _ifp_cluster_cache[cache_key] = response
    return response


def _file_identity(path: Path) -> tuple[str, int, int]:
    """Cheap freshness token: any rewrite or rename invalidates a cache key."""
    stat = path.stat()
    return (str(path), stat.st_size, stat.st_mtime_ns)


def _resolve_in_workspace(ws: Path, raw: str, field: str) -> Path:
    """Resolve a request path inside the workspace root; escapes are 422."""
    try:
        resolved = resolve_within(ws, raw)
    except ValueError as exc:
        raise InvalidInputError(f"{field} escapes the workspace: {raw}") from exc
    if not resolved.is_file():
        raise InvalidInputError(f"{field} not found: {raw}")
    return resolved
