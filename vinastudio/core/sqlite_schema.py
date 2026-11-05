"""Process-level cache for SQLite schema readiness (L21).

Every read path used to replay the full DDL and COMMIT. The cache is keyed by
the database file's path, mtime and size, so a migration from another process
(or a replaced file) invalidates it automatically.
"""

from __future__ import annotations

import os
import sqlite3

_READY: set[tuple[str, int, int]] = set()


def _identity(conn: sqlite3.Connection) -> tuple[str, int, int] | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None:
        return None
    path = str(row[2] or "")
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (path, stat.st_mtime_ns, stat.st_size)


def schema_is_ready(conn: sqlite3.Connection) -> bool:
    identity = _identity(conn)
    return identity is not None and identity in _READY


def mark_schema_ready(conn: sqlite3.Connection) -> None:
    identity = _identity(conn)
    if identity is not None:
        _READY.add(identity)
