"""Molecule library — search and fetch from RCSB PDB and PubChem."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from vinastudio.core.errors import ExternalServiceError, InvalidInputError
from vinastudio.core.paths import create_workspace, slugify

router = APIRouter(prefix="/library", tags=["library"])
log = logging.getLogger(__name__)

# --- RCSB endpoints (stable public API) ---

_RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
_RCSB_GRAPHQL_URL = "https://data.rcsb.org/graphql"
_RCSB_FILES_URL = "https://files.rcsb.org/download"
_RCSB_LIGAND_URL = "https://files.rcsb.org/ligands/download"

# Search timeout — RCSB can be slow on complex queries.
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# Maximum file size for downloads (50 MB). Larger files are likely errors.
_MAX_FILE_SIZE = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class LibrarySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Search term or PDB ID")
    rows: int = Field(default=20, ge=1, le=100)
    start: int = Field(default=0, ge=0)


class LibraryLigand(BaseModel):
    id: str
    name: str
    formula: str = ""
    molecularWeight: float | None = None


class LibraryChain(BaseModel):
    entityId: str = ""
    description: str = ""
    organism: str = ""
    sequenceLength: int = 0


class LibraryEntry(BaseModel):
    pdbId: str
    title: str
    method: str = ""
    resolution: float | None = None
    year: int | None = None
    authors: list[str] = []
    journal: str = ""
    doi: str = ""
    organism: str = ""
    ligands: list[LibraryLigand] = []
    chains: list[LibraryChain] = []
    entityCount: int = 0
    atomCount: int = 0
    molecularWeight: float | None = None
    moleculeType: str = "unknown"  # "protein", "rna", "dna", "hybrid", "unknown"


class LibrarySearchResponse(BaseModel):
    entries: list[LibraryEntry]
    totalCount: int


class LibraryFetchRequest(BaseModel):
    pdbId: str = Field(..., min_length=4, max_length=4, pattern=r"^[A-Za-z0-9]{4}$")
    kind: str = Field(default="receptor", pattern=r"^(receptor|ligand)$")
    ligandId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,10}$")


class LibraryFetchResponse(BaseModel):
    path: str
    name: str
    bytes: int
    pdbId: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GRAPHQL_ENTRY_QUERY = """{{
  entry(entry_id: "{pdb_id}") {{
    rcsb_id
    struct {{ title }}
    exptl {{ method }}
    rcsb_entry_info {{
      resolution_combined
      deposited_atom_count
      polymer_entity_count
      molecular_weight
    }}
    rcsb_primary_citation {{
      title
      pdbx_database_id_DOI
      year
      rcsb_authors
      journal_abbrev
    }}
    polymer_entities {{
      rcsb_polymer_entity {{ pdbx_description }}
      entity_poly {{
        pdbx_seq_one_letter_code_can
        rcsb_sample_sequence_length
      }}
      rcsb_entity_source_organism {{
        ncbi_scientific_name
      }}
    }}
    nonpolymer_entities {{
      nonpolymer_comp {{
        chem_comp {{ id name formula formula_weight }}
      }}
    }}
  }}
}}"""


def _detect_molecule_type(chains: list[dict]) -> str:
    """Detect molecule type from chain descriptions and sequences.

    Returns one of: "protein", "rna", "dna", "hybrid", "unknown".
    """
    has_protein = False
    has_rna = False
    has_dna = False

    for chain in chains:
        desc = (chain.get("description") or "").upper()
        seq = (chain.get("sequence") or "").upper()

        # Check description for RNA/DNA indicators (most reliable)
        is_rna_desc = (
            desc.startswith("R(")
            or "RNA" in desc
            or "RIBONUCLEIC" in desc
            or "MESSENGER RNA" in desc
            or "TRANSFER RNA" in desc
            or "SMALL INTERFERING RNA" in desc
            or "SIRNA" in desc
        )
        is_dna_desc = (
            desc.startswith("D(")
            or "DNA" in desc
            or "DEOXYRIBONUCLEIC" in desc
            or "DOUBLE-STRANDED DNA" in desc
        )

        # If description clearly indicates RNA/DNA, use that
        if is_rna_desc:
            has_rna = True
            continue
        if is_dna_desc:
            has_dna = True
            continue

        # For sequences, use composition analysis:
        # Nucleic acids are mostly A, C, G, T/U with very limited alphabet
        # Proteins have 20 standard amino acids with diverse composition
        if seq and len(seq) > 3:
            # Count nucleotide-only characters (excluding common amino acids)
            # U is only in RNA, T is in both (threonine + thymine)
            nuc_chars = set("ACGTU")

            # If sequence has U, it's likely RNA (U is not an amino acid)
            if "U" in seq:
                has_rna = True
                continue

            # Check if sequence is mostly nucleotides (low diversity)
            # Nucleic acids typically use only A, C, G, T
            seq_chars = set(seq)
            if seq_chars <= nuc_chars and len(seq_chars) <= 4:
                # Could be DNA or protein with only A, C, G, T
                # Use length and composition heuristics
                # DNA sequences are typically longer and have characteristic patterns
                if len(seq) > 10:
                    has_dna = True
                else:
                    has_protein = True
            else:
                has_protein = True
        elif desc:
            # If description exists but doesn't match RNA/DNA patterns, assume protein
            has_protein = True

    if has_protein and (has_rna or has_dna):
        return "hybrid"
    if has_rna and has_dna:
        return "hybrid"
    if has_rna:
        return "rna"
    if has_dna:
        return "dna"
    if has_protein:
        return "protein"
    return "unknown"


def _parse_entry(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract a clean dict from one GraphQL entry node."""
    if not raw:
        return None

    pdb_id = raw.get("rcsb_id", "")
    struct = raw.get("struct") or {}
    entry_info = raw.get("rcsb_entry_info") or {}
    citation = raw.get("rcsb_primary_citation") or {}
    exptl_list = raw.get("exptl") or []

    # Resolution is a list; take the first value.
    resolution_list = entry_info.get("resolution_combined") or []
    resolution = resolution_list[0] if resolution_list else None

    # Method from exptl list.
    method = exptl_list[0].get("method", "") if exptl_list else ""

    # Collect ligands, chains, organisms.
    ligands: list[dict] = []
    chains: list[dict] = []
    organism_set: set[str] = set()

    for pe in raw.get("polymer_entities") or []:
        entity = pe.get("rcsb_polymer_entity") or {}
        poly = pe.get("entity_poly") or {}
        src_orgs = pe.get("rcsb_entity_source_organism") or []

        for s in src_orgs:
            name = s.get("ncbi_scientific_name")
            if name:
                organism_set.add(name)
                break  # one per entity is enough

        chains.append({
            "entityId": entity.get("rcsb_id", "") or "",
            "description": entity.get("pdbx_description", "") or "",
            "organism": (src_orgs[0].get("ncbi_scientific_name") or "") if src_orgs else "",
            "sequenceLength": poly.get("rcsb_sample_sequence_length") or 0,
            "sequence": poly.get("pdbx_seq_one_letter_code_can", "") or "",
        })

    for npe in raw.get("nonpolymer_entities") or []:
        comp = (npe.get("nonpolymer_comp") or {}).get("chem_comp") or {}
        if comp:
            ligands.append({
                "id": comp.get("id", ""),
                "name": comp.get("name", ""),
                "formula": comp.get("formula", ""),
                "molecularWeight": comp.get("formula_weight"),
            })

    return {
        "pdbId": pdb_id.upper(),
        "title": struct.get("title", ""),
        "method": method,
        "resolution": resolution,
        "year": citation.get("year"),
        "authors": citation.get("rcsb_authors") or [],
        "journal": citation.get("journal_abbrev", ""),
        "doi": citation.get("pdbx_database_id_DOI") or "",
        "organism": ", ".join(sorted(organism_set)[:3]),
        "ligands": ligands,
        "chains": chains,
        "entityCount": entry_info.get("polymer_entity_count", 0),
        "atomCount": entry_info.get("deposited_atom_count", 0),
        "molecularWeight": entry_info.get("molecular_weight"),
        "moleculeType": _detect_molecule_type(chains),
    }


async def _rcsb_search(query: str, rows: int, start: int) -> dict[str, Any]:
    """Search RCSB PDB via the search API."""
    # If the query looks like a 4-character PDB ID, search by ID directly.
    if len(query) == 4 and query.isalnum():
        payload: dict[str, Any] = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_id",
                    "operator": "exact_match",
                    "value": query.upper(),
                },
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {"rows": rows, "start": start},
                "results_verbosity": "compact",
            },
        }
    else:
        payload = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": query},
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {"rows": rows, "start": start},
                "results_verbosity": "compact",
            },
        }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_RCSB_SEARCH_URL, json=payload)
        if resp.status_code == 204:
            return {"result_set": [], "total_count": 0}
        resp.raise_for_status()
        return resp.json()


async def _rcsb_graphql_entries(pdb_ids: list[str]) -> dict[str, dict]:
    """Batch-fetch entry metadata via GraphQL."""
    ids_literal = ", ".join(f'"{i.upper()}"' for i in pdb_ids)
    query = f"""{{
      entries(entry_ids: [{ids_literal}]) {{
        rcsb_id
        struct {{ title }}
        exptl {{ method }}
        rcsb_entry_info {{
          resolution_combined
          deposited_atom_count
          polymer_entity_count
          molecular_weight
        }}
        rcsb_primary_citation {{
          year
          rcsb_authors
          journal_abbrev
          pdbx_database_id_DOI
        }}
        polymer_entities {{
          rcsb_polymer_entity {{ pdbx_description }}
          entity_poly {{ rcsb_sample_sequence_length }}
          rcsb_entity_source_organism {{ ncbi_scientific_name }}
        }}
        nonpolymer_entities {{
          nonpolymer_comp {{ chem_comp {{ id name formula formula_weight }} }}
        }}
      }}
    }}"""

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_RCSB_GRAPHQL_URL, json={"query": query})
        resp.raise_for_status()
        data = resp.json()

    result: dict[str, dict] = {}
    # GraphQL can return {"data": null} on errors; guard against None.
    data_obj = data.get("data") or {}
    for entry in data_obj.get("entries") or []:
        if not entry:
            continue
        parsed = _parse_entry(entry)
        if parsed:
            result[parsed["pdbId"]] = parsed
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/search", response_model=LibrarySearchResponse)
async def search_library(req: LibrarySearchRequest) -> LibrarySearchResponse:
    """Search RCSB PDB for structures matching a query."""
    try:
        search_data = await _rcsb_search(req.query, req.rows, req.start)
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(f"RCSB search failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ExternalServiceError(f"RCSB search failed: {exc}") from exc
    except Exception as exc:
        raise ExternalServiceError(f"RCSB search failed: {exc}") from exc

    total = search_data.get("total_count", 0)
    raw_ids = search_data.get("result_set", [])

    # result_set is either ["1ABC", ...] (compact) or [{"identifier": "1ABC", ...}]
    pdb_ids = [
        (r if isinstance(r, str) else r.get("identifier", ""))
        for r in raw_ids
        if r
    ]

    if not pdb_ids:
        return LibrarySearchResponse(entries=[], totalCount=total)

    # Batch-fetch metadata (max 50 to avoid huge GraphQL responses).
    # Failures here are non-fatal: search results are still useful without metadata.
    try:
        meta = await _rcsb_graphql_entries(pdb_ids[:50])
    except Exception:  # noqa: BLE001 - non-fatal: search is still useful
        meta = {}

    entries = []
    for pid in pdb_ids:
        upper = pid.upper()
        info = meta.get(upper)
        if info:
            entries.append(LibraryEntry(**info))
        else:
            # Fallback: entry exists in search but metadata failed
            entries.append(LibraryEntry(pdbId=upper, title=""))

    return LibrarySearchResponse(entries=entries, totalCount=total)


@router.get("/entry/{pdb_id}", response_model=LibraryEntry)
async def get_entry_detail(pdb_id: str) -> LibraryEntry:
    """Fetch detailed metadata for a single PDB entry."""
    if len(pdb_id) != 4 or not pdb_id.isalnum():
        raise InvalidInputError("PDB ID must be exactly 4 alphanumeric characters")

    try:
        meta = await _rcsb_graphql_entries([pdb_id])
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(f"RCSB GraphQL failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ExternalServiceError(f"RCSB GraphQL failed: {exc}") from exc
    except Exception as exc:
        raise ExternalServiceError(f"RCSB GraphQL failed: {exc}") from exc

    info = meta.get(pdb_id.upper())
    if not info:
        raise InvalidInputError(f"Entry {pdb_id.upper()} not found in RCSB PDB")
    try:
        return LibraryEntry(**info)
    except Exception as exc:
        raise ExternalServiceError(f"Failed to parse entry data: {exc}") from exc


@router.post("/fetch", response_model=LibraryFetchResponse)
async def fetch_from_library(req: LibraryFetchRequest) -> LibraryFetchResponse:
    """Download a structure from RCSB PDB into the workspace."""
    pdb_id = req.pdbId.upper()

    if req.kind == "receptor":
        # Try PDB first; fall back to mmCIF for EM/NMR structures without PDB files.
        pdb_url = f"{_RCSB_FILES_URL}/{pdb_id}.pdb"
        cif_url = f"{_RCSB_FILES_URL}/{pdb_id}.cif"
        content: bytes | None = None
        used_filename = f"{pdb_id}.pdb"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # Attempt PDB download
            try:
                resp = await client.get(pdb_url)
                if resp.status_code == 200:
                    content = resp.content
            except httpx.RequestError:
                pass

            # Fallback to mmCIF if PDB not available
            if content is None or len(content) < 10:
                try:
                    resp = await client.get(cif_url)
                    if resp.status_code == 200 and len(resp.content) > 10:
                        content = resp.content
                        used_filename = f"{pdb_id}.cif"
                        log.info("PDB not available for %s, using mmCIF fallback", pdb_id)
                except httpx.RequestError:
                    pass

        if content is None or len(content) < 10:
            raise ExternalServiceError(
                f"RCSB download failed: no PDB or mmCIF file available for {pdb_id}"
            )
    else:
        # Ligand: use CCD ideal SDF
        if not req.ligandId:
            raise InvalidInputError("ligandId is required when kind=ligand")
        url = f"{_RCSB_LIGAND_URL}/{req.ligandId.upper()}_ideal.sdf"
        used_filename = f"{req.ligandId.upper()}.sdf"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(f"RCSB download failed: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ExternalServiceError(f"RCSB download failed: {exc}") from exc
        except Exception as exc:
            raise ExternalServiceError(f"RCSB download failed: {exc}") from exc

    if len(content) > _MAX_FILE_SIZE:
        raise ExternalServiceError(
            f"Downloaded file is too large ({len(content) / 1024 / 1024:.1f} MB); "
            f"maximum allowed is {_MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    try:
        ws = create_workspace(f"library-{pdb_id.lower()}")
        target = ws.file(used_filename)
        target.write_bytes(content)
    except OSError as exc:
        raise ExternalServiceError(
            f"failed to save file to workspace: {exc}"
        ) from exc

    return LibraryFetchResponse(
        path=str(target),
        name=used_filename,
        bytes=len(content),
        pdbId=pdb_id,
    )


class LibraryFetchAllRequest(BaseModel):
    pdbId: str = Field(..., min_length=4, max_length=4, pattern=r"^[A-Za-z0-9]{4}$")
    ligandIds: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("ligandIds")
    @classmethod
    def validate_ligand_ids(cls, v: list[str]) -> list[str]:
        for lid in v:
            if not lid or not lid.isalnum() or len(lid) > 10:
                raise ValueError(f"invalid ligand ID: {lid!r}")
        return v


class LibraryFetchAllResponse(BaseModel):
    receptor: LibraryFetchResponse
    ligands: list[LibraryFetchResponse]
    skipped: list[str] = Field(default_factory=list, description="Ligand IDs that failed to download or were too small/large")


@router.post("/fetch-all", response_model=LibraryFetchAllResponse)
async def fetch_all_from_library(req: LibraryFetchAllRequest) -> LibraryFetchAllResponse:
    """Download receptor PDB + all ligand SDFs from RCSB PDB in one call."""
    pdb_id = req.pdbId.upper()

    # Download receptor — try PDB first, fall back to mmCIF for EM/NMR structures.
    pdb_url = f"{_RCSB_FILES_URL}/{pdb_id}.pdb"
    cif_url = f"{_RCSB_FILES_URL}/{pdb_id}.cif"
    receptor_content: bytes | None = None
    receptor_filename = f"{pdb_id}.pdb"

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        # Attempt PDB download
        try:
            resp = await client.get(pdb_url)
            if resp.status_code == 200:
                receptor_content = resp.content
        except httpx.RequestError:
            pass

        # Fallback to mmCIF if PDB not available
        if receptor_content is None or len(receptor_content) < 10:
            try:
                resp = await client.get(cif_url)
                if resp.status_code == 200 and len(resp.content) > 10:
                    receptor_content = resp.content
                    receptor_filename = f"{pdb_id}.cif"
                    log.info("PDB not available for %s, using mmCIF fallback", pdb_id)
            except httpx.RequestError:
                pass

    if receptor_content is None or len(receptor_content) < 10:
        raise ExternalServiceError(
            f"RCSB receptor download failed: no PDB or mmCIF file available for {pdb_id}"
        )

    if len(receptor_content) > _MAX_FILE_SIZE:
        raise ExternalServiceError(
            f"Downloaded receptor file is too large ({len(receptor_content) / 1024 / 1024:.1f} MB); "
            f"maximum allowed is {_MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    ws = create_workspace(f"library-{pdb_id.lower()}")
    receptor_target = ws.file(receptor_filename)
    try:
        receptor_target.write_bytes(receptor_content)
    except OSError as exc:
        raise ExternalServiceError(
            f"failed to save receptor to workspace: {exc}"
        ) from exc

    receptor = LibraryFetchResponse(
        path=str(receptor_target),
        name=receptor_filename,
        bytes=len(receptor_content),
        pdbId=pdb_id,
    )

    # Download ligands (reuse a single HTTP client for efficiency)
    ligands: list[LibraryFetchResponse] = []
    skipped: list[str] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        for lig_id in req.ligandIds:
            lig_url = f"{_RCSB_LIGAND_URL}/{lig_id.upper()}_ideal.sdf"
            lig_filename = f"{lig_id.upper()}.sdf"
            try:
                resp = await client.get(lig_url)
                resp.raise_for_status()
                lig_content = resp.content
                if len(lig_content) < 10:
                    log.warning("ligand %s downloaded but content too small (%d bytes)", lig_id, len(lig_content))
                    skipped.append(lig_id.upper())
                    continue
                if len(lig_content) > _MAX_FILE_SIZE:
                    log.warning("ligand %s downloaded but content too large (%d bytes)", lig_id, len(lig_content))
                    skipped.append(lig_id.upper())
                    continue
                lig_target = ws.file(lig_filename)
                try:
                    lig_target.write_bytes(lig_content)
                except OSError as exc:
                    log.warning("failed to save ligand %s: %s", lig_id, exc)
                    skipped.append(lig_id.upper())
                    continue
                ligands.append(LibraryFetchResponse(
                    path=str(lig_target),
                    name=lig_filename,
                    bytes=len(lig_content),
                    pdbId=pdb_id,
                ))
            except httpx.HTTPStatusError as exc:
                log.warning("failed to download ligand %s: HTTP %d", lig_id, exc.response.status_code)
                skipped.append(lig_id.upper())
            except httpx.RequestError as exc:
                log.warning("failed to download ligand %s: %s", lig_id, exc)
                skipped.append(lig_id.upper())

    return LibraryFetchAllResponse(receptor=receptor, ligands=ligands, skipped=skipped)


# ---------------------------------------------------------------------------
# PubChem PUG-REST provider — one precise small-molecule query at a time
# (TASK-11). User-triggered only, results are not cached: PubChem usage terms.
# ---------------------------------------------------------------------------

_PUG_COMPOUND_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"

# PubChem caps anonymous clients at ~5 requests/second; a sliding window keeps
# a burst of user clicks inside that budget (task §8).
_PUG_RATE_LIMIT = 5
_PUG_RATE_WINDOW = 1.0
_PUG_TIMES: deque[float] = deque()

# Single-compound SDFs are a few kB; anything near this cap is a runaway answer.
_PUG_MAX_FILE_SIZE = 5 * 1024 * 1024

# Test seam: tests inject httpx.MockTransport here so the suite never dials out.
_PUG_TRANSPORT: httpx.AsyncBaseTransport | None = None

# InChIKey is 14-10-1 uppercase blocks; a compound name never matches this shape.
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


class PubChemFetchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Compound name, SMILES, CID (digits) or InChIKey",
    )


class PubChemFetchResponse(BaseModel):
    path: str
    name: str
    bytes: int
    cid: int


async def _pug_throttle() -> None:
    """Take one token from the 5 req/s window, sleeping past the budget."""
    while True:
        now = time.monotonic()
        while _PUG_TIMES and now - _PUG_TIMES[0] >= _PUG_RATE_WINDOW:
            _PUG_TIMES.popleft()
        if len(_PUG_TIMES) < _PUG_RATE_LIMIT:
            _PUG_TIMES.append(now)
            return
        await asyncio.sleep(max(_PUG_RATE_WINDOW - (now - _PUG_TIMES[0]), 0.001))


def _pug_client() -> httpx.AsyncClient:
    kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "follow_redirects": True}
    if _PUG_TRANSPORT is not None:
        kwargs["transport"] = _PUG_TRANSPORT
    return httpx.AsyncClient(**kwargs)


async def _pug_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET a PUG-REST URL with throttling and offline/service error mapping."""
    await _pug_throttle()
    try:
        return await client.get(url)
    except httpx.RequestError as exc:
        # Timeouts subclass RequestError; either way the client can retry later.
        raise ExternalServiceError("无网络或 PubChem 不可达") from exc


async def _pug_resolve(client: httpx.AsyncClient, namespace: str, value: str) -> list[int]:
    """Map an identifier to PubChem CIDs.

    404 (name unknown) and 400 (value not valid for this namespace, e.g. text
    that is not SMILES) both mean "this namespace cannot answer" → empty list;
    only rate limits and upstream faults raise.
    """
    url = f"{_PUG_COMPOUND_URL}/{namespace}/{quote(value, safe='')}/cids/JSON"
    resp = await _pug_get(client, url)
    if resp.status_code in (400, 404):
        return []
    if resp.status_code == 429:
        raise ExternalServiceError("PubChem 请求过于频繁，请稍后重试")
    if resp.status_code != 200:
        raise ExternalServiceError(f"PubChem 服务异常 (HTTP {resp.status_code})")
    try:
        identifier_list = resp.json()["IdentifierList"]
        # The live API spells the key "CID" (verified against the name, smiles
        # and cid namespaces on 2026-09-28); "cid" stays as a fallback so a
        # spelling drift parses instead of becoming a misleading 502.
        raw = identifier_list.get("CID") or identifier_list.get("cid")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ExternalServiceError("PubChem 返回了非预期的内容") from exc
    if raw is None:
        raise ExternalServiceError("PubChem 返回了非预期的内容")
    return [int(c) for c in raw]


async def _pug_fetch_3d(client: httpx.AsyncClient, cid: int) -> bytes:
    """Download the 3D SDF for one CID; never silently fall back to 2D (task §4.2)."""
    url = f"{_PUG_COMPOUND_URL}/cid/{cid}/SDF?record_type=3d"
    resp = await _pug_get(client, url)
    if resp.status_code == 404:
        raise InvalidInputError("该条目无 3D 构象")
    if resp.status_code == 429:
        raise ExternalServiceError("PubChem 请求过于频繁，请稍后重试")
    if resp.status_code != 200:
        raise ExternalServiceError(f"PubChem 服务异常 (HTTP {resp.status_code})")
    content = resp.content
    if len(content) > _PUG_MAX_FILE_SIZE:
        raise ExternalServiceError(
            f"下载文件过大（超过 {(_PUG_MAX_FILE_SIZE + 1024 * 1024 - 1) // (1024 * 1024)} MB）"
        )
    # A 200 HTML error page parses as text but is not a mol block.
    if b"M  END" not in content:
        raise ExternalServiceError("PubChem 返回了非预期的内容（不是 SDF）")
    return content


@router.post("/pubchem/fetch", response_model=PubChemFetchResponse)
async def fetch_from_pubchem(req: PubChemFetchRequest) -> PubChemFetchResponse:
    """Fetch one compound's 3D SDF from PubChem into ``ligands/``.

    The stored SDF is not parameterised here: the client feeds it through the
    regular file-ligand inspect path. Identifier routing — digits are a CID,
    an InChIKey shape is exact; anything else is tried as a name first and as
    SMILES second, so arbitrary text ends as "not found" rather than an error.
    """
    query = req.query.strip()
    if not query:
        raise InvalidInputError("查询不能为空")

    if query.isdigit():
        attempts = [("cid", query)]
    elif _INCHIKEY_RE.match(query.upper()):
        attempts = [("inchikey", query.upper())]
    else:
        attempts = [("name", query), ("smiles", query)]

    async with _pug_client() as client:
        cids: list[int] = []
        for namespace, value in attempts:
            cids = await _pug_resolve(client, namespace, value)
            if cids:
                break
        if not cids:
            raise InvalidInputError("PubChem 未找到该条目")
        # Ambiguous names resolve to many CIDs; take the first exact match
        # and surface it in the response (task §8).
        cid = cids[0]
        content = await _pug_fetch_3d(client, cid)

    from vinastudio.core.workspace import ligands_dir
    from vinastudio.server.routers.ligand import _unique_sdf_path
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    # No active workspace (tests / first launch): fall back to an ephemeral run
    # directory so the endpoint still returns a readable path (ligand.py pattern).
    dest_dir = ligands_dir(ws) if ws is not None else create_workspace("pubchem").path
    stem = f"pubchem-{cid}" if query.isdigit() else f"{slugify(query, fallback='pubchem')}-{cid}"
    target = _unique_sdf_path(dest_dir, stem)
    try:
        target.write_bytes(content)
    except OSError as exc:
        raise ExternalServiceError(f"保存到工作区失败: {exc}") from exc

    # The SDF's first line is PubChem's compound title — show that, not the
    # query.  But PubChem often emits a bare CID as the title (imatinib is
    # "5291"), and an empty line names nothing: echo the query instead so the
    # toast and the stored name never show a naked number (MANUAL §13.1a).
    title = content.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
    name = query if not title or title.isdigit() else title
    return PubChemFetchResponse(
        path=str(target),
        name=name,
        bytes=len(content),
        cid=cid,
    )
