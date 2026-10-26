"""Server-side catalog search: FTS5, structured filters and facets."""

from __future__ import annotations

import re
import shlex
import sqlite3
from pathlib import Path
from typing import Any

from vinastudio.core.catalog.db import connect, ensure_schema

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_SORTS = {
    "updated": "m.updated_at DESC, m.name COLLATE NOCASE",
    "name": "m.name COLLATE NOCASE ASC, m.updated_at DESC",
    "weight": "m.molecular_weight IS NULL, m.molecular_weight ASC, m.name COLLATE NOCASE",
    "created": "m.created_at DESC, m.name COLLATE NOCASE",
    "rank": "bm25(molecule_fts), m.name COLLATE NOCASE",
}
_KNOWN_FIELDS = {
    "type", "kind", "role", "status", "prep", "prepared", "source",
    "tag", "study", "collection", "mw", "qed", "lipinski",
    "tpsa", "logp", "hbd", "hba", "rotatable",
}
_MW_RE = re.compile(r"^(?:(>=|<=|>|<))?(-?\d+(?:\.\d+)?)(?:-(-?\d+(?:\.\d+)?))?$")


def _quote_fts(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _looks_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _parse_query(q: str) -> tuple[str, dict[str, list[str]]]:
    """Split free text from ``field:value`` filters.

    Quoted values are kept together; unknown fields remain free text. This is
    intentionally small and explicit rather than a general query language.
    """
    text_parts: list[str] = []
    filters: dict[str, list[str]] = {}
    # ``shlex`` handles quoted phrases without a nested regex; the previous
    # expression had overlapping alternatives and was polynomial on long input.
    try:
        tokens = shlex.split(q)
    except ValueError:
        tokens = q.split()
    for token in tokens:
        field, separator, value = token.partition(":")
        if separator and field.lower() in _KNOWN_FIELDS and value:
            filters.setdefault(field.lower(), []).append(value)
        else:
            text_parts.append(token)
    return " ".join(text_parts), filters


def _add_filter(
    where: list[str],
    params: list[Any],
    column: str,
    values: list[str],
    *,
    numeric: bool = False,
) -> None:
    if not values:
        return
    clauses = []
    for value in values:
        if numeric:
            match = _MW_RE.match(value)
            if match is None:
                continue
            op, low, high = match.groups()
            if high is not None:
                clauses.append(f"{column} BETWEEN ? AND ?")
                params.extend([float(low), float(high)])
            else:
                operator = op or "="
                clauses.append(f"{column} {operator} ?")
                params.append(float(low))
        else:
            clauses.append(f"{column} = ?")
            params.append(value)
    if clauses:
        where.append("(" + " OR ".join(clauses) + ")")


def _build_where(
    q: str, filters: dict[str, list[str]]
) -> tuple[str, list[Any], str | None, str]:
    """Return ``(where_sql, params, fts_text, sort_default)``."""
    where: list[str] = []
    params: list[Any] = []
    fts_text: str | None = None
    free_text, parsed = _parse_query(q)
    for key, values in parsed.items():
        if key in {"type", "kind"}:
            _add_filter(where, params, "m.kind_hint", values)
        elif key == "status":
            _add_filter(where, params, "m.status", values)
        elif key in {"prep", "prepared"}:
            _add_filter(where, params, "m.prep_status", values)
        elif key == "source":
            clauses = []
            for value in values:
                clauses.append("m.source = ?")
                params.append(value)
                clauses.append(
                    "EXISTS (SELECT 1 FROM molecule_sources s WHERE s.molecule_id = m.id AND s.source = ?)"
                )
                params.append(value)
            if clauses:
                where.append("(" + " OR ".join(clauses) + ")")
        elif key == "tag":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM molecule_tags mt WHERE mt.molecule_id = m.id AND mt.tag = ?)"
                )
                params.append(value)
        elif key == "study":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM study_members sm JOIN studies s ON s.id = sm.study_id "
                    "WHERE sm.molecule_id = m.id AND s.name = ?)"
                )
                params.append(value)
        elif key == "collection":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM collection_members cm JOIN collections c ON c.id = cm.collection_id "
                    "WHERE cm.molecule_id = m.id AND c.name = ?)"
                )
                params.append(value)
        elif key == "role":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM study_members sm WHERE sm.molecule_id = m.id AND sm.role = ?)"
                )
                params.append(value)
        elif key == "mw":
            _add_filter(where, params, "m.molecular_weight", values, numeric=True)
        elif key in {"qed", "lipinski", "tpsa", "logp", "hbd", "hba", "rotatable"}:
            column = {
                "qed": "m.qed",
                "lipinski": "m.lipinski_violations",
                "tpsa": "m.tpsa",
                "logp": "m.clogp",
                "hbd": "m.hbd",
                "hba": "m.hba",
                "rotatable": "m.rotatable_bonds",
            }[key]
            _add_filter(where, params, column, values, numeric=True)

    for key, value in (filters or {}).items():
        values = value if isinstance(value, list) else [value]
        values = [str(item) for item in values if item not in (None, "")]
        if not values:
            continue
        if key in {"kind", "kind_hint"}:
            _add_filter(where, params, "m.kind_hint", values)
        elif key == "status":
            _add_filter(where, params, "m.status", values)
        elif key in {"prep_status", "prep"}:
            _add_filter(where, params, "m.prep_status", values)
        elif key == "source":
            _add_filter(where, params, "m.source", values)
        elif key == "tag":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM molecule_tags mt WHERE mt.molecule_id = m.id AND mt.tag = ?)"
                )
                params.append(value)
        elif key == "study_id":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM study_members sm WHERE sm.molecule_id = m.id AND sm.study_id = ?)"
                )
                params.append(value)
        elif key == "collection_id":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM collection_members cm WHERE cm.molecule_id = m.id AND cm.collection_id = ?)"
                )
                params.append(value)
        elif key == "library_id":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM library_members lm WHERE lm.molecule_id = m.id AND lm.library_id = ?)"
                )
                params.append(value)
        elif key == "role":
            for value in values:
                where.append(
                    "EXISTS (SELECT 1 FROM study_members sm WHERE sm.molecule_id = m.id AND sm.role = ?)"
                )
                params.append(value)
        elif key == "mw_min":
            where.append("m.molecular_weight >= ?")
            params.append(float(values[0]))
        elif key == "mw_max":
            where.append("m.molecular_weight <= ?")
            params.append(float(values[0]))
        elif key == "unassigned":
            where.append("NOT EXISTS (SELECT 1 FROM study_members sm WHERE sm.molecule_id = m.id)")

    if free_text:
        tokens = [token for token in free_text.split() if token]
        if tokens:
            fts_text = " AND ".join(_quote_fts(token) for token in tokens)
    return " AND ".join(where), params, fts_text, "rank" if fts_text else "updated"


def _text_fallback(q: str) -> str:
    """Short CJK queries are not reliable through unicode61 FTS tokens."""
    return q.strip()


def search_molecules(
    *,
    q: str = "",
    filters: dict[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    sort: str = "updated",
    db_path: Path | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    where_sql, params, fts_text, default_sort = _build_where(q, filters or {})
    order = _SORTS.get(sort, _SORTS[default_sort])

    clauses = []
    if where_sql:
        clauses.append(where_sql)
    fallback = bool(fts_text and _looks_cjk(fts_text) and len(fts_text.strip('"')) < 3)
    if fts_text and not fallback:
        clauses.append("molecule_fts MATCH ?")
        params_match = [*params, fts_text]
    elif fts_text and fallback:
        # LIKE fallback for two-character CJK names. It remains bounded by the
        # same structured filters and is only used below the FTS trigram limit.
        terms = [item.strip('"') for item in fts_text.split(' AND ')]
        for term in terms:
            clauses.append("(m.name LIKE ? OR m.search_text LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
        params_match = params
    else:
        params_match = params

    join = "JOIN molecule_fts ON molecule_fts.rowid = m.rowid" if fts_text and not fallback else ""
    where_expr = " AND ".join(clauses) if clauses else "1=1"
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        total = int(conn.execute(
            f"SELECT COUNT(*) FROM molecules m {join} WHERE {where_expr}", params_match
        ).fetchone()[0])
        rows = conn.execute(
            f"""SELECT m.*,
                       (SELECT path FROM molecule_files
                        WHERE molecule_id = m.id AND kind IN ('sdf', 'pdb', 'pdbqt')
                        ORDER BY is_primary DESC, kind LIMIT 1) AS primary_path
                FROM molecules m {join}
                WHERE {where_expr}
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
            [*params_match, limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            data = dict(row)
            data["metadata"] = _json_or_empty(data.pop("metadata_json", "{}"))
            items.append(data)
        facets = _facets(conn, where_expr, params_match, join)
    finally:
        conn.close()
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": facets,
    }


def _json_or_empty(value: str) -> dict[str, Any]:
    import json

    try:
        parsed = json.loads(value or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _facets(
    conn: sqlite3.Connection,
    where_expr: str,
    params: list[Any],
    join: str,
) -> dict[str, list[dict[str, Any]]]:
    """Build source/status/prep facets in one scan, tags in one join.

    The three scalar facets share the same filtered set, so grouping by their
    combined tuple avoids three separate passes with the same correlated
    ``EXISTS`` predicates. Top-20 ordering is applied in Python.
    """
    rows = conn.execute(
        f"""SELECT m.source AS source, m.status AS status,
                   m.prep_status AS prep, COUNT(*) AS count
            FROM molecules m {join}
            WHERE {where_expr}
            GROUP BY m.source, m.status, m.prep_status""",
        params,
    ).fetchall()
    counters: dict[str, dict[str, int]] = {"source": {}, "status": {}, "prep": {}}
    for row in rows:
        count = int(row["count"])
        for facet, column in (("source", "source"), ("status", "status"), ("prep", "prep")):
            value = row[column]
            if value is not None:
                counters[facet][str(value)] = counters[facet].get(str(value), 0) + count

    def top(values: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count}
            for value, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]

    tags = conn.execute(
        f"""SELECT mt.tag AS value, COUNT(*) AS count
            FROM molecules m {join}
            JOIN molecule_tags mt ON mt.molecule_id = m.id
            WHERE {where_expr}
            GROUP BY mt.tag ORDER BY count DESC, value LIMIT 20""",
        params,
    ).fetchall()
    return {
        "source": top(counters["source"]),
        "status": top(counters["status"]),
        "prep": top(counters["prep"]),
        "tags": [dict(row) for row in tags],
    }



def _matching_parts(
    *, q: str = "", filters: dict[str, Any] | None = None
) -> tuple[list[str], list[Any], str, str]:
    where_sql, params, fts_text, _ = _build_where(q, filters or {})
    clauses = [where_sql] if where_sql else []
    fallback = bool(fts_text and _looks_cjk(fts_text) and len(fts_text.strip('"')) < 3)
    if fts_text and not fallback:
        clauses.append("molecule_fts MATCH ?")
        params_match = [*params, fts_text]
    elif fts_text and fallback:
        for term in [item.strip('"') for item in fts_text.split(' AND ')]:
            clauses.append("(m.name LIKE ? OR m.search_text LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
        params_match = params
    else:
        params_match = params
    join = "JOIN molecule_fts ON molecule_fts.rowid = m.rowid" if fts_text and not fallback else ""
    where_expr = " AND ".join(clauses) if clauses else "1=1"
    return clauses, params_match, join, where_expr


def matching_rows(
    *,
    q: str = "",
    filters: dict[str, Any] | None = None,
    limit: int = 20000,
    db_path: Path | None = None,
) -> list[dict[str, str]]:
    """Resolve a catalog query to ``(id, identity_key)`` snapshot rows.

    This is the one place bulk selection resolves a query server-side; callers
    never need to receive every id in the browser. Ordering is stable enough
    for a frozen snapshot; later ranking belongs to the run, not the selector.
    """
    _, params_match, join, where_expr = _matching_parts(q=q, filters=filters)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            f"SELECT m.id, m.identity_key FROM molecules m {join} "
            "WHERE {where_expr} ORDER BY m.updated_at DESC, m.name COLLATE NOCASE LIMIT ?".format(
                where_expr=where_expr
            ),
            [*params_match, max(1, min(limit, 50000))],
        ).fetchall()
    finally:
        conn.close()
    return [{"id": str(row["id"]), "identity_key": str(row["identity_key"])} for row in rows]


def matching_count(
    *, q: str = "", filters: dict[str, Any] | None = None, db_path: Path | None = None
) -> int:
    """Number of rows matching the same filters, without materialising ids."""
    _, params_match, join, where_expr = _matching_parts(q=q, filters=filters)
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            f"SELECT COUNT(*) FROM molecules m {join} WHERE {where_expr}", params_match
        ).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row is not None else 0


def matching_ids(
    *,
    q: str = "",
    filters: dict[str, Any] | None = None,
    limit: int = 20000,
    db_path: Path | None = None,
) -> list[str]:
    """Every matching molecule id, bounded for legacy bulk operations."""
    return [
        item["id"]
        for item in matching_rows(q=q, filters=filters, limit=limit, db_path=db_path)
    ]
