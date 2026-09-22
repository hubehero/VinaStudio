"""Molecule library — search and fetch from RCSB PDB."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from vinastudio.core.errors import ExternalServiceError, InvalidInputError
from vinastudio.core.paths import create_workspace

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
        url = f"{_RCSB_FILES_URL}/{pdb_id}.pdb"
        filename = f"{pdb_id}.pdb"
    else:
        # Ligand: use CCD ideal SDF
        if not req.ligandId:
            raise InvalidInputError("ligandId is required when kind=ligand")
        url = f"{_RCSB_LIGAND_URL}/{req.ligandId.upper()}_ideal.sdf"
        filename = f"{req.ligandId.upper()}.sdf"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(f"RCSB download failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ExternalServiceError(f"RCSB download failed: {exc}") from exc
    except Exception as exc:
        raise ExternalServiceError(f"RCSB download failed: {exc}") from exc

    content = resp.content
    if len(content) < 10:
        raise ExternalServiceError("Downloaded file is empty or too small")
    if len(content) > _MAX_FILE_SIZE:
        raise ExternalServiceError(
            f"Downloaded file is too large ({len(content) / 1024 / 1024:.1f} MB); "
            f"maximum allowed is {_MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    try:
        ws = create_workspace(f"library-{pdb_id.lower()}")
        target = ws.file(filename)
        target.write_bytes(content)
    except OSError as exc:
        raise ExternalServiceError(
            f"failed to save file to workspace: {exc}"
        ) from exc

    return LibraryFetchResponse(
        path=str(target),
        name=filename,
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

    # Download receptor
    receptor_url = f"{_RCSB_FILES_URL}/{pdb_id}.pdb"
    receptor_filename = f"{pdb_id}.pdb"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(receptor_url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(f"RCSB receptor download failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ExternalServiceError(f"RCSB receptor download failed: {exc}") from exc

    receptor_content = resp.content
    if len(receptor_content) < 10:
        raise ExternalServiceError("Downloaded receptor file is empty or too small")
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
