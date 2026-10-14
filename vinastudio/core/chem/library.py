"""Compound libraries for the virtual screening workbench (TASK-13).

A library is ``<workspace>/libraries/<name>/`` with one single-molecule SDF
per record (``mols/NNNNNN.sdf``) and an ``index.json`` manifest.  The import
is a streaming record split: a multi-record SDF never lands in memory whole,
and the per-molecule byte cap needs the raw record text, which
``ForwardSDMolSupplier`` discards — so records are framed by ``$$$$`` here.

Two invariants the rest of the task relies on:

- ``entry["index"]`` is the record ordinal among *everything* seen during the
  import (imported, failed and skipped records alike) and equals the zero
  padded file name — failures leave visible gaps rather than shifting names.
- ``prepare`` is never truth from the manifest: the PDBQT on disk is the
  truth, and the server repairs the field on read (§4.1).  Workers may write
  the ``.failed`` marker but never ``index.json``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rdkit import Chem

from vinastudio.config import lib_max_mol_bytes, lib_max_mols
from vinastudio.core import paths
from vinastudio.core.chem.properties import canonical_smiles, descriptor_bundle
from vinastudio.core.errors import InvalidInputError

log = logging.getLogger(__name__)

INDEX_FILENAME = "index.json"
MOLS_DIRNAME = "mols"

#: Library names become URL path segments (``GET /libraries/{name}``), so they
#: are restricted to a boring ASCII slug instead of escaping arbitrary text.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: The failed list ships at most this many rows; ``failedCount`` stays exact.
MAX_FAILED_LISTED = 100

#: Failure reasons, verbatim from the wire contract (design §3).
REASON_PARSE = "parse"
REASON_TOO_LARGE = "too_large"
REASON_CAP = "cap"
REASON_WRITE = "write"


class LibraryExistsError(FileExistsError):
    """A library with this name already exists (router maps it to 409)."""


@dataclass(frozen=True)
class FailedEntry:
    index: int
    name: str
    reason: str


@dataclass
class ImportReport:
    """Result of one import; ``imported + skipped + failed_count`` equals the
    number of records seen across all sources."""

    name: str
    imported: int = 0
    skipped: int = 0
    failed_count: int = 0
    created: float = 0.0
    failed: list[FailedEntry] = field(default_factory=list)


def is_valid_name(name: str | None) -> bool:
    return bool(name and _NAME_RE.match(name))


def validate_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    if not is_valid_name(cleaned):
        raise InvalidInputError(f"invalid library name: {name!r}")
    return cleaned


def libraries_root(root: Path | None = None) -> Path:
    """``<workspace>/libraries`` — sibling of ``jobs/`` in both layouts."""
    if root is not None:
        return root
    ws_root = paths.workspace_root()
    base = ws_root.parent if ws_root.name == "jobs" else ws_root
    return base / "libraries"


def library_dir(name: str, root: Path | None = None) -> Path:
    return libraries_root(root) / validate_name(name)


def library_exists(name: str, root: Path | None = None) -> bool:
    try:
        return (library_dir(name, root) / INDEX_FILENAME).is_file()
    except InvalidInputError:
        return False


def entry_sdf_path(libdir: Path, index: int) -> Path:
    return libdir / MOLS_DIRNAME / f"{index:06d}.sdf"


def entry_pdbqt_path(libdir: Path, index: int) -> Path:
    return libdir / MOLS_DIRNAME / f"{index:06d}.pdbqt"


def _failed_marker(libdir: Path, index: int) -> Path:
    return libdir / MOLS_DIRNAME / f"{index:06d}.failed"


def prepare_status(libdir: Path, index: int) -> str:
    """Read-time truth: PDBQT on disk wins, then the worker's failure marker."""
    if entry_pdbqt_path(libdir, index).is_file():
        return "done"
    if _failed_marker(libdir, index).is_file():
        return "failed"
    return "none"


def mark_prepare_failed(libdir: Path, index: int, reason: str) -> None:
    """Record a failed prepare attempt (worker side; index.json stays untouched)."""
    try:
        _failed_marker(libdir, index).write_text(reason, encoding="utf-8")
    except OSError:
        log.warning("could not write prepare marker for %s#%d", libdir.name, index)


def clear_prepare_failure(libdir: Path, index: int) -> None:
    try:
        _failed_marker(libdir, index).unlink(missing_ok=True)
    except OSError:
        log.warning("could not clear prepare marker for %s#%d", libdir.name, index)


def _iter_sdf_records(path: Path) -> Iterator[tuple[bytes, str]]:
    """Yield ``(record_bytes, title)`` per SDF record, one line at a time."""
    buf: list[bytes] = []
    with path.open("rb") as fh:
        for line in fh:
            buf.append(line)
            if line.strip() == b"$$$$":
                record = b"".join(buf)
                buf = []
                yield record, _title(record)
    if buf and any(line.strip() for line in buf):
        record = b"".join(buf)
        yield record, _title(record)


def _title(record: bytes) -> str:
    first = record.split(b"\n", 1)[0].strip()
    if not first or first == b"$$$$":
        return ""
    return first.decode("utf-8", errors="replace")


def _record_failure(report: ImportReport, index: int, name: str, reason: str) -> None:
    report.failed_count += 1
    if len(report.failed) < MAX_FAILED_LISTED:
        report.failed.append(FailedEntry(index=index, name=name, reason=reason))


def import_library(
    name: str,
    sources: Sequence[Path | str],
    *,
    root: Path | None = None,
) -> ImportReport:
    """Split source SDFs into a new library; raises on name/duplicate errors."""
    name = validate_name(name)
    if not sources:
        raise InvalidInputError("library import needs at least one source file")
    libdir = library_dir(name, root)
    if (libdir / INDEX_FILENAME).exists():
        raise LibraryExistsError(name)
    mols_dir = libdir / MOLS_DIRNAME
    mols_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = lib_max_mol_bytes()
    cap = lib_max_mols()
    report = ImportReport(name=name, created=time.time())
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    ordinal = 0

    def handle(record: bytes, title: str) -> None:
        nonlocal ordinal
        index = ordinal
        ordinal += 1
        mol_name = title or f"mol_{index}"

        if report.imported >= cap:
            _record_failure(report, index, mol_name, REASON_CAP)
            return
        if len(record) > max_bytes:
            _record_failure(report, index, mol_name, REASON_TOO_LARGE)
            return
        try:
            mol = Chem.MolFromMolBlock(
                record.decode("utf-8", errors="replace"),
                removeHs=False,
                sanitize=True,
            )
        except Exception:  # noqa: BLE001 - malformed input is a per-record failure
            mol = None
        if mol is None:
            _record_failure(report, index, mol_name, REASON_PARSE)
            return

        smiles = canonical_smiles(mol)
        key = f"{mol_name}\n{smiles or ''}"
        if key in seen:
            report.skipped += 1
            return
        seen.add(key)

        try:
            entry_sdf_path(libdir, index).write_bytes(record)
        except OSError:
            _record_failure(report, index, mol_name, REASON_WRITE)
            return

        try:
            bundle: dict[str, object] = dict(descriptor_bundle(mol))
        except Exception:  # noqa: BLE001 - descriptors are best effort
            bundle = {"molWt": None, "qed": None, "lipinskiViolations": None}
        entries.append({
            "index": index,
            "name": mol_name,
            "file": f"{MOLS_DIRNAME}/{index:06d}.sdf",
            "prepare": "none",
            **bundle,
        })
        report.imported += 1

    for source in (Path(s) for s in sources):
        try:
            record_iter = iter(_iter_sdf_records(source))
            # Pull the first record outside the loop so an unreadable file is
            # reported once instead of being swallowed by a lazy generator.
            first = next(record_iter, None)
        except OSError:
            _record_failure(report, ordinal, source.name, REASON_PARSE)
            ordinal += 1
            continue
        if first is not None:
            handle(*first)
        for record, title in record_iter:
            handle(record, title)

    payload = {
        "schemaVersion": 1,
        "name": name,
        "created": report.created,
        "entries": entries,
    }
    tmp = libdir / f"{INDEX_FILENAME}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, libdir / INDEX_FILENAME)
    return report


def _read_index(libdir: Path) -> dict | None:
    index_path = libdir / INDEX_FILENAME
    if not index_path.is_file():
        return None
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        log.warning("unreadable library index at %s", index_path)
        return None
    return data if isinstance(data, dict) else None


def _entry_rows(libdir: Path, entries: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not isinstance(entries, list):
        return rows
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("index"))
        except (TypeError, ValueError):
            continue
        rows.append({
            "index": index,
            "name": str(raw.get("name") or f"mol_{index}"),
            "molWt": raw.get("molWt"),
            "qed": raw.get("qed"),
            "lipinskiViolations": raw.get("lipinskiViolations"),
            "prepare": prepare_status(libdir, index),
        })
    return rows


def list_libraries(root: Path | None = None) -> list[dict[str, object]]:
    """All importable libraries, newest first (wire shape: LibrarySummary)."""
    base = libraries_root(root)
    if not base.is_dir():
        return []
    summaries: list[dict[str, object]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        data = _read_index(child)
        if data is None:
            continue
        rows = _entry_rows(child, data.get("entries"))
        summaries.append({
            "name": child.name,
            "total": len(rows),
            "prepared": sum(1 for row in rows if row["prepare"] == "done"),
            "created": float(data.get("created") or 0.0),
        })
    summaries.sort(key=lambda row: row["created"], reverse=True)
    return summaries


def load_detail(name: str, root: Path | None = None) -> dict[str, object] | None:
    """Full entry list with prepare repaired on read; None = unknown library."""
    try:
        libdir = library_dir(name, root)
    except InvalidInputError:
        return None
    data = _read_index(libdir)
    if data is None:
        return None
    rows = _entry_rows(libdir, data.get("entries"))
    return {
        "name": libdir.name,
        "total": len(rows),
        "created": float(data.get("created") or 0.0),
        "entries": rows,
    }
