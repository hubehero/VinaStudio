"""Workspace-level results index for cross-project search (TASK-15).

``job.json`` files stay the source of truth — this SQLite database is only
an index over their terminal snapshots.  Ingestion is idempotent by
``job_id`` and callers are expected to degrade failures to warnings: a
broken index can never fail the docking run that feeds it (§6.3).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from rdkit import Chem

from vinastudio.core import paths
from vinastudio.core.chem.ligand_prep import _canonical_smiles
from vinastudio.core.chem.pdbqt import _SMILES_RE
from vinastudio.core.paths import (
    BATCH_RESULTS_CSV_FILENAME,
    JOB_STATE_FILENAME,
    POSES_SDF_FILENAME,
    SCREENING_JSONL_FILENAME,
)

log = logging.getLogger(__name__)

#: The only statuses worth indexing — anything else is still in flight.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

#: Search bounds (task book §4.3): empty q returns the latest rows.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

#: Raw structure payloads are megabytes, not readable parameters.  They are
#: stripped from ``params_json`` (both the camelCase spellings the legacy
#: strip list knows and the snake_case ones production actually writes) while
#: ``params_hash`` still hashes the full params, so identical configurations
#: keep de-duplicating.  ``ligands`` is the batch roster, ``entries`` its
#: screening twin (one name+index per library molecule) — likewise bulk.
_PARAMS_JSON_DROP = frozenset({
    "ligandPdbqtString",
    "receptorPdbqtString",
    "pdbqtString",
    "ligand_pdbqt_string",
    "receptor_pdbqt_string",
    "ligands",
    "entries",
})

_SCHEMA_VERSION = 2

#: sqlite connections are created per call and closed immediately; the lock
#: only serialises writers inside this process (event-loop thread vs the
#: FastAPI threadpool — design §10).
_WRITE_LOCK = threading.Lock()


class ResultsDbError(RuntimeError):
    """The index exists but cannot be used (schema too new, corrupt file)."""


def results_db_path() -> Path:
    """``<workspace>/results.sqlite`` — beside the jobs root, for both layouts.

    ``paths.workspace_root()`` is ``<ws>/jobs`` when a workspace is
    configured and ``<app_home>/workspace`` otherwise; the index sits in the
    parent directory so ``artifact_ref`` relative paths resolve the same way
    in either layout.
    """
    root = paths.workspace_root()
    parent = root.parent if root.name == "jobs" else root
    return parent / "results.sqlite"


_TABLE_DDL = (
    """CREATE TABLE IF NOT EXISTS runs (
        job_id TEXT PRIMARY KEY,
        label TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL,
        status TEXT NOT NULL,
        receptor TEXT NOT NULL DEFAULT '',
        scoring TEXT NOT NULL DEFAULT '',
        is_batch INTEGER NOT NULL DEFAULT 0,
        best_affinity REAL,
        elapsed_ms INTEGER,
        params_json TEXT,
        params_hash TEXT,
        n_poses INTEGER NOT NULL DEFAULT 0,
        favorite INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS poses (
        run_id TEXT NOT NULL REFERENCES runs(job_id) ON DELETE CASCADE,
        pose_index INTEGER NOT NULL,
        ligand_name TEXT NOT NULL DEFAULT '',
        ligand_smiles TEXT,
        affinity REAL NOT NULL,
        rmsd_lb REAL NOT NULL,
        rmsd_ub REAL NOT NULL,
        artifact_ref TEXT,
        PRIMARY KEY (run_id, pose_index)
    )""",
    # Per-ligand rows for search (TASK-13 §4.7): batch rows are handed in
    # from the manager's state, screening rows are re-read from
    # screening.jsonl — the jsonl is append-only and idempotent under the
    # same delete-then-insert rule the poses table follows.
    """CREATE TABLE IF NOT EXISTS screening_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        ligand_name TEXT,
        ligand_smiles TEXT,
        affinity REAL
    )""",
    """CREATE TABLE IF NOT EXISTS run_tags (
        run_id TEXT NOT NULL REFERENCES runs(job_id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        PRIMARY KEY (run_id, tag)
    )""",
    """CREATE TABLE IF NOT EXISTS saved_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        filters_json TEXT NOT NULL,
        created REAL NOT NULL
    )""",
)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create or migrate the index; refuse a schema newer than this build.

    v2 adds favourites, tags and saved views.  The migration is additive:
    an existing v1 database gains a ``favorite`` column and the two new
    tables, while ingest never rewrites favourite/tags, so rebuilding the
    index cannot erase a user's organisation.
    """
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    version = int(row["version"]) if row is not None else 0
    if version > _SCHEMA_VERSION:
        raise ResultsDbError(f"results schema v{version} newer than supported v{_SCHEMA_VERSION}")

    for ddl in _TABLE_DDL:
        conn.execute(ddl)

    # ``CREATE TABLE IF NOT EXISTS`` does not add a column to an old table.
    columns = {item[1] for item in conn.execute("PRAGMA table_info(runs)")}
    if "favorite" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")

    if row is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,)
        )
    elif version < _SCHEMA_VERSION:
        conn.execute("UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,))
    conn.commit()


def _header_smiles(text: str) -> str | None:
    """Canonical SMILES from a prepared PDBQT's Meeko header, or None.

    job.json itself never carries a SMILES (design §10); a header that does
    not parse must degrade to NULL — name/receptor matching still works.
    """
    raw: str | None = None
    for line in text.splitlines():
        match = _SMILES_RE.match(line)
        if match:
            raw = match.group(1)
            break
    if not raw:
        return None
    mol = Chem.MolFromSmiles(raw)
    if mol is None:
        log.debug("results ingest: header SMILES %r did not parse", raw)
        return None
    return _canonical_smiles(mol)


def _ligand_smiles(params: dict[str, Any]) -> str | None:
    ligand_path = params.get("ligand_path")
    if isinstance(ligand_path, str) and ligand_path:
        try:
            text = Path(ligand_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        return _header_smiles(text)
    inline = params.get("ligand_pdbqt_string")
    if isinstance(inline, str) and inline:
        return _header_smiles(inline)
    return None


def _run_label(payload: dict[str, Any], params: dict[str, Any]) -> str:
    # Design §3 defines label as the ligand/task name with a fallback to the
    # ligand file name.  Production never fills it truthfully (upstream
    # ``_job_label`` looks up the camelCase key while the router passes
    # snake_case — F1), so a path-based run is named by its file.
    if payload.get("isBatch"):
        roster = params.get("ligands")
        if isinstance(roster, list):
            names = []
            for entry in roster:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("label")
                if not isinstance(name, str) or not name:
                    path = entry.get("ligandPath")
                    name = Path(path).name if isinstance(path, str) and path else ""
                if name:
                    names.append(name)
            if names:
                # Keep the row readable; the full roster stays in params_json.
                suffix = f" (+{len(names) - 1})" if len(names) > 1 else ""
                return f"{names[0]}{suffix}"
    ligand_path = params.get("ligand_path")
    if isinstance(ligand_path, str) and ligand_path:
        return Path(ligand_path).name
    return str(payload.get("label") or "")


def _receptor_name(params: dict[str, Any]) -> str:
    receptor_path = params.get("receptor_path")
    if isinstance(receptor_path, str) and receptor_path:
        return Path(receptor_path).name
    return ""


def _best_affinity(payload: dict[str, Any], status: str, is_batch: bool) -> float | None:
    # Mirror ``routers/docking._summary_best_affinity``: JobState.best_affinity
    # defaults to 0.0 and a batch never writes it, so a literal copy would
    # show "0.00" for failed and batch runs — the jobs list computes these.
    if status != "completed":
        return None
    if not is_batch:
        value = payload.get("bestAffinity")
        return float(value) if isinstance(value, (int, float)) else None
    scored = [
        float(row["bestAffinity"])
        for row in payload.get("batchResults") or []
        if isinstance(row, dict) and isinstance(row.get("bestAffinity"), (int, float))
    ]
    return min(scored) if scored else None


def _float_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _artifact_ref(job_id: str, db_path: Path) -> str | None:
    """Workspace-relative address of the pose coordinates, when on disk.

    Poses themselves never enter the DB (task book §4.1); a run that died
    before writing the SDF keeps a NULL reference instead of a dangling one.
    """
    sdf = paths.workspace_root() / job_id / POSES_SDF_FILENAME
    if not sdf.is_file():
        return None
    try:
        return sdf.relative_to(db_path.parent).as_posix()
    except ValueError:
        return f"jobs/{job_id}/{POSES_SDF_FILENAME}"


def _pose_rows(
    payload: dict[str, Any],
    job_id: str,
    label: str,
    smiles: str | None,
    artifact_ref: str | None,
) -> list[tuple[Any, ...]]:
    poses = payload.get("poses")
    if not isinstance(poses, list):
        return []
    rows: list[tuple[Any, ...]] = []
    for pose in poses:
        if not isinstance(pose, dict):
            continue
        affinity = pose.get("affinity")
        rmsd_lb = pose.get("rmsdLower")
        rmsd_ub = pose.get("rmsdUpper")
        # PoseInfo (design §3) has non-null floats; a pose missing any of
        # these cannot honour the contract, so it is not indexed.
        if not all(isinstance(v, (int, float)) for v in (affinity, rmsd_lb, rmsd_ub)):
            continue
        rows.append((
            job_id,
            int(pose.get("index") or 0),
            label,
            smiles,
            float(affinity),
            float(rmsd_lb),
            float(rmsd_ub),
            artifact_ref,
        ))
    return rows


def _item_row(job_id: str, name: Any, smiles: Any, affinity: Any) -> tuple[Any, ...]:
    return (
        job_id,
        str(name) if name is not None else "",
        str(smiles) if isinstance(smiles, str) else None,
        _float_or_none(affinity),
    )


def _screening_item_rows(job_id: str) -> list[tuple[Any, ...]]:
    """Terminal rows of this run's ``screening.jsonl`` (§4.7).

    Read-only and best effort: a missing or torn file yields what it has —
    the append-only writer (job_manager, single lock) is the source of truth
    and this reader must never block the ingest it feeds.
    """
    try:
        text = (
            paths.workspace_root() / job_id / SCREENING_JSONL_FILENAME
        ).read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[tuple[Any, ...]] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("status") not in {"completed", "failed"}:
            continue
        rows.append(_item_row(job_id, row.get("name"), row.get("smiles"), row.get("affinity")))
    return rows


def _batch_item_rows(job_id: str, rows: list[Any]) -> list[tuple[Any, ...]]:
    return [
        _item_row(job_id, row.get("label"), row.get("smiles"), row.get("bestAffinity"))
        for row in rows
        if isinstance(row, dict)
    ]


def _csv_float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _csv_int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_batch_results_csv(text: str) -> list[dict[str, Any]] | None:
    """Parse the full-ranking artifact back into batch row dicts.

    ``None`` means the text was unreadable — callers then fall back to the
    top slice stored in ``job.json``.  This is the single column mapping for
    ``batch_results.csv``: the server restore path and the startup backfill
    both parse through it so the two cannot drift (TASK-27 勘误 ⑩).  The
    artifact never carried SMILES, so rows carry ``None`` there — never a
    placeholder string.
    """
    rows: list[dict[str, Any]] = []
    try:
        for raw in csv.DictReader(io.StringIO(text)):
            rows.append({
                "ligandIndex": int(raw.get("ligand_index") or 0),
                "label": raw.get("label") or "",
                "status": raw.get("status") or "",
                "bestAffinity": _csv_float_or_none(raw.get("best_affinity_kcal_mol")),
                "nPoses": int(raw.get("pose_count") or 0),
                "elapsedMs": None,
                "outDir": "",
                "error": raw.get("error") or "",
                "qed": _csv_float_or_none(raw.get("qed")),
                "lipinskiViolations": _csv_int_or_none(raw.get("lipinski_violations")),
                "smiles": None,  # the CSV artifact never carried SMILES
            })
    except (ValueError, csv.Error):
        log.warning("batch results CSV is unreadable", exc_info=True)
        return None
    return rows


def batch_ligand_rows(
    payload: dict[str, Any], *, root: Path | None = None
) -> list[dict[str, Any]] | None:
    """Complete per-ligand rows for a batch index, or ``None`` when absent.

    Row-source priority (TASK-27 §4.2): an untruncated ``batchResults`` is
    the full set; a truncated index falls back to the CSV artifact; truncated
    without that artifact (a run killed mid-flight) yields ``None`` — the top
    slice must never masquerade as the complete ranking, so the ingest stays
    run-level for that window.  Non-batch payloads have no per-ligand rows.
    """
    if not payload.get("isBatch"):
        return None
    if not payload.get("batchResultsTruncated"):
        rows = payload.get("batchResults")
        return list(rows) if isinstance(rows, list) else None
    job_id = str(payload.get("jobId") or "")
    if not job_id:
        return None
    scan_root = root or paths.workspace_root()
    try:
        text = (
            scan_root / job_id / BATCH_RESULTS_CSV_FILENAME
        ).read_text(encoding="utf-8")
    except OSError:
        return None  # truncated with no artifact: run-level only
    return parse_batch_results_csv(text)


def ingest_job_payload(
    payload: dict[str, Any],
    *,
    db_path: Path | None = None,
    ligand_rows: list[Any] | None = None,
) -> bool:
    """Upsert one terminal ``job.json`` payload; idempotent by ``job_id``.

    Returns True when a row was written, False for non-terminal payloads.
    ``ligand_rows`` are the full per-ligand batch rows from the manager's
    state (TASK-13 §4.7); without them a batch ingests run-level data only —
    the truncated ``batchResults`` slice would index a silently partial set.
    Screening runs ignore it and read ``screening.jsonl`` themselves, which
    keeps the startup backfill complete too.  sqlite errors propagate —
    callers wrap this in try/except (§6.3).
    """
    status = str(payload.get("status") or "")
    if status not in TERMINAL_STATUSES:
        return False
    job_id = str(payload.get("jobId") or "")
    if not job_id:
        return False

    db = db_path or results_db_path()
    raw_params = payload.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}
    is_batch = bool(payload.get("isBatch"))
    label = _run_label(payload, params)
    elapsed = payload.get("elapsedMs")
    n_poses = payload.get("nPoses")
    readable = {k: v for k, v in params.items() if k not in _PARAMS_JSON_DROP}
    params_json = json.dumps(readable, ensure_ascii=False, sort_keys=True)
    params_hash = hashlib.sha256(
        json.dumps(params, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    pose_rows: list[tuple[Any, ...]] = []
    if not is_batch:
        pose_rows = _pose_rows(
            payload,
            job_id,
            label,
            _ligand_smiles(params),
            _artifact_ref(job_id, db),
        )

    # Per-ligand search rows (TASK-13 §4.7): screening reads its jsonl
    # (works for the startup backfill too); batch only indexes rows the
    # caller vouches for — the truncated payload slice is not enough.
    if payload.get("isScreening"):
        item_rows = _screening_item_rows(job_id)
    elif is_batch and ligand_rows is not None:
        item_rows = _batch_item_rows(job_id, ligand_rows)
    else:
        item_rows = []

    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT INTO runs (
                       job_id, label, created, status, receptor, scoring,
                       is_batch, best_affinity, elapsed_ms, params_json,
                       params_hash, n_poses
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                       label=excluded.label, created=excluded.created,
                       status=excluded.status, receptor=excluded.receptor,
                       scoring=excluded.scoring, is_batch=excluded.is_batch,
                       best_affinity=excluded.best_affinity,
                       elapsed_ms=excluded.elapsed_ms,
                       params_json=excluded.params_json,
                       params_hash=excluded.params_hash,
                       n_poses=excluded.n_poses""",
                (
                    job_id,
                    label,
                    float(payload.get("createdAt") or 0.0),
                    status,
                    _receptor_name(params),
                    str(payload.get("scoring") or ""),
                    int(is_batch),
                    _best_affinity(payload, status, is_batch),
                    int(elapsed) if isinstance(elapsed, (int, float)) else None,
                    params_json,
                    params_hash,
                    int(n_poses) if isinstance(n_poses, (int, float)) else 0,
                ),
            )
            # A re-ingest replaces the pose set wholesale — that is what makes
            # the startup backfill safe to run on every launch.
            conn.execute("DELETE FROM poses WHERE run_id = ?", (job_id,))
            conn.executemany(
                """INSERT INTO poses (
                       run_id, pose_index, ligand_name, ligand_smiles,
                       affinity, rmsd_lb, rmsd_ub, artifact_ref
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                pose_rows,
            )
            # Same rule for the per-ligand rows: 续跑重终态不重复 (§4.7).
            conn.execute("DELETE FROM screening_items WHERE run_id = ?", (job_id,))
            conn.executemany(
                """INSERT INTO screening_items (
                       run_id, ligand_name, ligand_smiles, affinity
                   ) VALUES (?, ?, ?, ?)""",
                item_rows,
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return True


_SEARCH_SQL = """
SELECT r.job_id, r.label, r.created, r.receptor, r.scoring, r.status,
       r.best_affinity, r.is_batch, r.favorite,
       (SELECT GROUP_CONCAT(t.tag, char(31)) FROM run_tags t
        WHERE t.run_id = r.job_id) AS tags_concat,
       CASE
         WHEN :needle = '' OR instr(lower(r.label), :needle) > 0 THEN NULL
         ELSE (
           SELECT m.name FROM (
             SELECT p.ligand_name AS name FROM poses p
             WHERE p.run_id = r.job_id
               AND (instr(lower(p.ligand_name), :needle) > 0
                    OR (p.ligand_smiles IS NOT NULL
                        AND instr(lower(p.ligand_smiles), :needle) > 0))
             UNION ALL
             SELECT s.ligand_name AS name FROM screening_items s
             WHERE s.run_id = r.job_id
               AND (instr(lower(s.ligand_name), :needle) > 0
                    OR (s.ligand_smiles IS NOT NULL
                        AND instr(lower(s.ligand_smiles), :needle) > 0))
             LIMIT 1
           ) AS m
         )
       END AS matched_ligand
FROM runs r
WHERE (
   :needle = ''
   OR instr(lower(r.label), :needle) > 0
   OR instr(lower(r.receptor), :needle) > 0
   OR EXISTS (
       SELECT 1 FROM poses p2
       WHERE p2.run_id = r.job_id
         AND (instr(lower(p2.ligand_name), :needle) > 0
              OR (p2.ligand_smiles IS NOT NULL
                  AND instr(lower(p2.ligand_smiles), :needle) > 0))
   )
   OR EXISTS (
       SELECT 1 FROM screening_items s2
       WHERE s2.run_id = r.job_id
         AND (instr(lower(s2.ligand_name), :needle) > 0
              OR (s2.ligand_smiles IS NOT NULL
                  AND instr(lower(s2.ligand_smiles), :needle) > 0))
   )
)
AND (:favorites = 0 OR r.favorite = 1)
/*TAG_FILTER*/
ORDER BY r.created DESC, r.job_id DESC
LIMIT :limit
OFFSET :offset
"""


def _summary(row: sqlite3.Row) -> dict[str, Any]:
    # ``sqlite3.Row`` membership tests iterate values, not column names, so
    # this reads the column directly — every row comes from _SEARCH_SQL,
    # which always projects matched_ligand.
    return {
        "jobId": row["job_id"],
        "label": row["label"],
        "createdAt": row["created"],
        "receptor": row["receptor"],
        "scoring": row["scoring"],
        "status": row["status"],
        "bestAffinity": row["best_affinity"],
        "isBatch": bool(row["is_batch"]),
        "favorite": bool(row["favorite"]),
        "tags": _split_tags(row["tags_concat"]),
        "matchedLigand": row["matched_ligand"],
    }


def _split_tags(value: str | None) -> list[str]:
    return [tag for tag in (value or "").split(chr(31)) if tag]


def search_runs(
    q: str = "",
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    favorites: bool = False,
    tags: list[str] | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Latest-first substring search over label ∪ receptor ∪ poses.

    ``tags`` uses AND semantics: every requested tag must be present.  Missing
    DB → warning + ``[]``; a corrupt file raises so the router can degrade it
    to ``[]`` too (design §3, never a 500).  ``offset`` pages the same stable
    ordering (``created`` then ``job_id``, both descending).
    """
    db = db_path or results_db_path()
    bounded = max(1, min(int(limit), MAX_LIMIT))
    bounded_offset = max(0, int(offset))
    if not db.is_file():
        log.warning("results db missing at %s — returning no rows", db)
        return []
    needle = (q or "").lower()
    wanted = list(dict.fromkeys(tag for tag in (tags or []) if tag))
    params: dict[str, Any] = {
        "needle": needle,
        "limit": bounded,
        "offset": bounded_offset,
        "favorites": int(bool(favorites)),
    }
    tag_filter = ""
    if wanted:
        placeholders = []
        for index, tag in enumerate(wanted):
            key = f"tag{index}"
            placeholders.append(f":{key}")
            params[key] = tag
        params["tag_count"] = len(wanted)
        tag_filter = (
            "AND r.job_id IN ("
            "SELECT rt.run_id FROM run_tags rt "
            f"WHERE rt.tag IN ({', '.join(placeholders)}) "
            "GROUP BY rt.run_id HAVING COUNT(DISTINCT rt.tag) = :tag_count)"
        )
    with closing(_connect(db)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            _SEARCH_SQL.replace("/*TAG_FILTER*/", tag_filter), params
        ).fetchall()
    return [_summary(row) for row in rows]


def _detail(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    params: dict[str, Any] | None = None
    if row["params_json"]:
        try:
            parsed = json.loads(row["params_json"])
            params = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            log.warning("results: unreadable params_json for %s", row["job_id"])
    pose_rows = conn.execute(
        """SELECT pose_index, affinity, rmsd_lb, rmsd_ub FROM poses
           WHERE run_id = ? ORDER BY pose_index""",
        (row["job_id"],),
    ).fetchall()
    return {
        "jobId": row["job_id"],
        "label": row["label"],
        "createdAt": row["created"],
        "receptor": row["receptor"],
        "scoring": row["scoring"],
        "status": row["status"],
        "bestAffinity": row["best_affinity"],
        "isBatch": bool(row["is_batch"]),
        "favorite": bool(row["favorite"]),
        "tags": [
            item["tag"]
            for item in conn.execute(
                "SELECT tag FROM run_tags WHERE run_id = ? ORDER BY tag",
                (row["job_id"],),
            ).fetchall()
        ],
        "matchedLigand": None,
        "params": params,
        "nPoses": row["n_poses"],
        "elapsedMs": row["elapsed_ms"],
        "poses": [
            {
                "index": pose["pose_index"],
                "affinity": pose["affinity"],
                "rmsdLower": pose["rmsd_lb"],
                "rmsdUpper": pose["rmsd_ub"],
            }
            for pose in pose_rows
        ],
    }


def compare_runs(run_ids: list[str], *, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Details for the requested ids, in request order; unknown ids skipped."""
    db = db_path or results_db_path()
    if not db.is_file():
        log.warning("results db missing at %s — returning no rows", db)
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for run_id in run_ids:
        if run_id and run_id not in seen:
            seen.add(run_id)
            ordered.append(run_id)
    if not ordered:
        return []
    details: list[dict[str, Any]] = []
    with closing(_connect(db)) as conn:
        _ensure_schema(conn)
        for run_id in ordered:
            row = conn.execute("SELECT * FROM runs WHERE job_id = ?", (run_id,)).fetchone()
            if row is None:
                continue  # 静默跳过（design §10）
            details.append(_detail(conn, row))
    return details


def backfill(
    *,
    db_path: Path | None = None,
    root: Path | None = None,
    known: list[tuple[Path, Any]] | None = None,
) -> int:
    """Index every terminal ``job.json`` not yet in the DB (startup repair).

    Returns the number of runs written this call.  Two repair passes, both
    idempotent (the backfill runs at every launch): an unindexed run gains
    its per-ligand rows from the complete source; an already-indexed batch
    whose rows never landed — the crash window before ``ligand_rows`` reached
    the ingest — is re-ingested once a complete source exists.  Non-batch
    runs, runs whose rows already exist, and windows without a complete
    source are left untouched (task book §4.2).

    ``known`` hands the caller's already-parsed ``(index, payload)`` pairs
    straight through — the startup path passes what ``restore_history`` just
    read so the payloads are parsed once, not twice; the disk scan only
    happens when ``known is None`` (task book P2-A).
    """
    db = db_path or results_db_path()
    scan_root = root or paths.workspace_root()
    if not scan_root.is_dir():
        return 0
    indexed = 0
    if known is None:
        for entry in sorted(scan_root.iterdir()):
            index = entry / JOB_STATE_FILENAME
            if not index.is_file():
                continue  # prep runs and stray directories
            try:
                payload = json.loads(index.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                log.warning("results backfill: skipping unreadable %s", index, exc_info=True)
                continue
            if _backfill_one(index, payload, db_path=db, scan_root=scan_root):
                indexed += 1
    else:
        for index, payload in known:
            if _backfill_one(index, payload, db_path=db, scan_root=scan_root):
                indexed += 1
    return indexed


def _backfill_one(index: Path, payload: Any, *, db_path: Path, scan_root: Path) -> bool:
    """Index a single parsed ``job.json``; True when a run row was written."""
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status") or "") not in TERMINAL_STATUSES:
        return False
    entry = index.parent
    job_id = str(payload.get("jobId") or entry.name)
    try:
        with closing(_connect(db_path)) as conn:
            _ensure_schema(conn)
            if conn.execute("SELECT 1 FROM runs WHERE job_id = ?", (job_id,)).fetchone():
                # Repair pass: only a batch with zero per-ligand rows and
                # a complete source on hand qualifies; everything else is
                # already up to date.
                if not payload.get("isBatch"):
                    return False
                if conn.execute(
                    "SELECT 1 FROM screening_items WHERE run_id = ? LIMIT 1",
                    (job_id,),
                ).fetchone():
                    return False  # rows landed: nothing to rewrite
                rows = batch_ligand_rows(payload, root=scan_root)
                if not rows:
                    # 0 or unavailable: never re-ingest a truncated slice
                    # and never loop on an empty set.
                    return False
            else:
                rows = batch_ligand_rows(payload, root=scan_root)
        return ingest_job_payload(
            {**payload, "jobId": job_id}, db_path=db_path, ligand_rows=rows
        )
    except (sqlite3.Error, OSError, ResultsDbError) as exc:
        # One bad run must not stop the rest of the scan.
        log.warning("results backfill failed for %s: %s", job_id, exc, exc_info=True)
        return False


# ── organisation: favourites, tags, saved views (TASK-49) ────────────────────

_MAX_TAGS_PER_RUN = 20
_MAX_TAG_LENGTH = 40


def _normalise_tags(tags: list[str]) -> list[str]:
    """Trim, drop empties, dedupe, and enforce the small per-run bounds."""
    normalised: list[str] = []
    for raw in tags:
        tag = str(raw).strip()
        if not tag:
            continue
        if len(tag) > _MAX_TAG_LENGTH:
            raise ValueError(f"tag is longer than {_MAX_TAG_LENGTH} characters")
        if "," in tag:
            raise ValueError("tag may not contain commas")
        if tag not in normalised:
            normalised.append(tag)
    if len(normalised) > _MAX_TAGS_PER_RUN:
        raise ValueError(f"at most {_MAX_TAGS_PER_RUN} tags per run")
    return normalised


def set_run_favorite(
    job_id: str, favorite: bool, *, db_path: Path | None = None
) -> bool:
    """Set the favourite flag; False when the run is not indexed."""
    db = db_path or results_db_path()
    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "UPDATE runs SET favorite = ? WHERE job_id = ?",
            (int(bool(favorite)), job_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def set_run_tags(job_id: str, tags: list[str], *, db_path: Path | None = None) -> bool:
    """Replace all tags for one run; False when the run is not indexed."""
    normalised = _normalise_tags(tags)
    db = db_path or results_db_path()
    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute(
            "SELECT 1 FROM runs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if exists is None:
            conn.rollback()
            return False
        conn.execute("DELETE FROM run_tags WHERE run_id = ?", (job_id,))
        conn.executemany(
            "INSERT INTO run_tags (run_id, tag) VALUES (?, ?)",
            [(job_id, tag) for tag in normalised],
        )
        conn.commit()
        return True


def bulk_update_runs(
    run_ids: list[str],
    *,
    favorite: bool | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    db_path: Path | None = None,
) -> int:
    """Apply a favourite/tag operation to the existing runs only.

    Tags are idempotent; adding an existing tag or removing a missing one is
    not an error.  Returns the number of indexed runs the request matched.
    """
    ids = list(dict.fromkeys(run_id for run_id in run_ids if run_id))
    if not ids:
        return 0
    add = _normalise_tags(add_tags or [])
    remove = _normalise_tags(remove_tags or [])
    db = db_path or results_db_path()
    placeholders = ", ".join("?" for _ in ids)
    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        existing = [
            row["job_id"]
            for row in conn.execute(
                f"SELECT job_id FROM runs WHERE job_id IN ({placeholders})", ids
            ).fetchall()
        ]
        if favorite is not None and existing:
            conn.executemany(
                "UPDATE runs SET favorite = ? WHERE job_id = ?",
                [(int(bool(favorite)), run_id) for run_id in existing],
            )
        if add:
            conn.executemany(
                "INSERT OR IGNORE INTO run_tags (run_id, tag) VALUES (?, ?)",
                [(run_id, tag) for run_id in existing for tag in add],
            )
        if remove:
            conn.executemany(
                "DELETE FROM run_tags WHERE run_id = ? AND tag = ?",
                [(run_id, tag) for run_id in existing for tag in remove],
            )
        conn.commit()
        return len(existing)


def list_tags(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Distinct tags with their run counts, alphabetical."""
    db = db_path or results_db_path()
    if not db.is_file():
        return []
    with closing(_connect(db)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT tag, COUNT(*) AS count FROM run_tags GROUP BY tag ORDER BY lower(tag)"
        ).fetchall()
    return [{"tag": row["tag"], "count": int(row["count"])} for row in rows]


def get_run_organization(
    job_id: str, *, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Favourite + tags for one run, or None when it is not indexed."""
    db = db_path or results_db_path()
    if not db.is_file():
        return None
    with closing(_connect(db)) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT favorite FROM runs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        tags = [
            item["tag"]
            for item in conn.execute(
                "SELECT tag FROM run_tags WHERE run_id = ? ORDER BY tag", (job_id,)
            ).fetchall()
        ]
    return {"favorite": bool(row["favorite"]), "tags": tags}


def _view_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        parsed = json.loads(row["filters_json"])
        filters = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        filters = {}
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "filters": filters,
        "createdAt": float(row["created"]),
    }


def save_view(
    name: str, filters: dict[str, Any], *, db_path: Path | None = None
) -> dict[str, Any]:
    """Create or replace a saved filter view by name."""
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 60:
        raise ValueError("view name must be 1–60 characters")
    db = db_path or results_db_path()
    payload = json.dumps(filters, ensure_ascii=False, sort_keys=True)
    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO saved_views (name, filters_json, created)
               VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   filters_json = excluded.filters_json,
                   created = excluded.created""",
            (clean_name, payload, time.time()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, filters_json, created FROM saved_views WHERE name = ?",
            (clean_name,),
        ).fetchone()
    assert row is not None
    return _view_row(row)


def list_views(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    db = db_path or results_db_path()
    if not db.is_file():
        return []
    with closing(_connect(db)) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT id, name, filters_json, created FROM saved_views ORDER BY name"
        ).fetchall()
    return [_view_row(row) for row in rows]


def delete_view(view_id: int, *, db_path: Path | None = None) -> bool:
    db = db_path or results_db_path()
    with _WRITE_LOCK, closing(_connect(db)) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
        conn.commit()
        return cursor.rowcount > 0
