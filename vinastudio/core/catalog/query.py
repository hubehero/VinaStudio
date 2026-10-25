"""Server-side catalog search: FTS5, structured filters and facets."""

from __future__ import annotations

import re
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
}
_MW_RE = re.compile(r"^(?:(>=|<=|>|<))?(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?$")


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
    token_re = re.compile(r'([^\s:"()]+):("([^"]*)"|[^\s]+)|"([^"]*)"|(\S+)')
    for match in token_re.finditer(q.strip()):
        field = match.group(1)
        if field and field.lower() in _KNOWN_FIELDS:
            value = match.group(3) if match.group(3) is not None else match.group(2)
            filters.setdefault(field.lower(), []).append(value)
        else:
            text_parts.append(match.group(4) or match.group(5) or match.group(0))
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
        elif key in {"qed", "lipinski"}:
            column = "m.qed" if key == "qed" else "m.lipinski_violations"
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
    def grouped(column: str, table_alias: str = "m") -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""SELECT {table_alias}.{column} AS value, COUNT(*) AS count
                FROM molecules m {join}
                WHERE {where_expr} AND {table_alias}.{column} IS NOT NULL
                GROUP BY {table_alias}.{column}
                ORDER BY count DESC, value LIMIT 20""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    tags = conn.execute(
        f"""SELECT mt.tag AS value, COUNT(*) AS count
            FROM molecules m {join}
            JOIN molecule_tags mt ON mt.molecule_id = m.id
            WHERE {where_expr}
            GROUP BY mt.tag ORDER BY count DESC, value LIMIT 20""",
        params,
    ).fetchall()
    return {
        "source": grouped("source"),
        "status": grouped("status"),
        "prep": grouped("prep_status"),
        "tags": [dict(row) for row in tags],
    }


def matching_ids(
    *,
    q: str = "",
    filters: dict[str, Any] | None = None,
    limit: int = 20000,
    db_path: Path | None = None,
) -> list[str]:
    """Every matching molecule id, bounded for bulk operations.

    The catalog UI may select results across pages; the server resolves the
    same query once instead of shipping every row to the browser.
    """
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
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            f"SELECT m.id FROM molecules m {join} WHERE {where_expr} "
            "ORDER BY m.updated_at DESC, m.name COLLATE NOCASE LIMIT ?",
            [*params_match, max(1, min(limit, 50000))],
        ).fetchall()
    finally:
        conn.close()
    return [str(row["id"]) for row in rows]
