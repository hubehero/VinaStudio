"""Compound search providers (PubChem, ChEMBL) for the molecule library.

The existing RCSB and PubChem quick-fetch endpoints stay in ``library.py``.
These endpoints are additive: the interface can browse a provider, choose a
compound, and then download it without changing the old contracts.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter

from vinastudio.core.chem.compound_sources import SOURCES, source_info
from vinastudio.core.errors import ExternalServiceError, InvalidInputError
from vinastudio.core.paths import create_workspace, slugify
from vinastudio.schemas.compound_library import (
    CompoundFetchRequest,
    CompoundFetchResponse,
    CompoundSearchPage,
    CompoundSearchRequest,
    CompoundSourceInfo,
)

router = APIRouter(prefix="/library", tags=["library"])

#: Search pages are cached in memory only; provider data is never mirrored.
_CACHE_TTL = 300.0
_CACHE_MAX = 128
_CACHE: dict[tuple[Any, ...], tuple[float, CompoundSearchPage]] = {}
_CACHE_LOCK = asyncio.Lock()


def _cache_key(request: CompoundSearchRequest) -> tuple[Any, ...]:
    return (
        request.source,
        request.mode,
        request.query.strip(),
        request.limit,
        request.offset,
        request.threshold,
    )


async def _cached_search(request: CompoundSearchRequest) -> CompoundSearchPage:
    key = _cache_key(request)
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
        if cached:
            _CACHE.pop(key, None)

    source = SOURCES[request.source]
    page = await source.search(
        request.query,
        request.mode,
        request.limit,
        request.offset,
        request.threshold,
    )
    async with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (now + _CACHE_TTL, page)
    return page


@router.get("/sources", response_model=list[CompoundSourceInfo])
def list_compound_sources() -> list[CompoundSourceInfo]:
    return [CompoundSourceInfo(**item) for item in source_info()]


@router.post("/compounds/search", response_model=CompoundSearchPage)
async def search_compounds(request: CompoundSearchRequest) -> CompoundSearchPage:
    try:
        return await _cached_search(request)
    except InvalidInputError:
        raise
    except ExternalServiceError:
        raise
    except Exception as exc:
        raise ExternalServiceError(f"{request.source} search failed: {exc}") from exc


@router.post("/compounds/fetch", response_model=CompoundFetchResponse)
async def fetch_compound(request: CompoundFetchRequest) -> CompoundFetchResponse:
    source = SOURCES[request.source]
    content, has3d = await source.fetch(request.id)

    from vinastudio.core.workspace import ligands_dir
    from vinastudio.server.routers.ligand import _unique_sdf_path
    from vinastudio.server.routers.workspace import get_active_workspace

    ws = get_active_workspace()
    dest_dir = ligands_dir(ws) if ws is not None else create_workspace("compounds").path
    stem = f"{request.source}-{slugify(request.id, fallback='compound')}"
    target = _unique_sdf_path(dest_dir, stem)
    try:
        target.write_bytes(content)
    except OSError as exc:
        raise ExternalServiceError(f"保存到工作区失败: {exc}") from exc

    return CompoundFetchResponse(
        path=str(target),
        name=target.name,
        bytes=len(content),
        source=request.source,
        sourceId=request.id,
        has3D=has3d,
        license=source.license,
    )
