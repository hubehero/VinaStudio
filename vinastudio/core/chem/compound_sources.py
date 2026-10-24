"""Online compound providers for the molecule library.

The providers deliberately return a small, common projection instead of each
service's full payload: the UI only needs an identifier, a name, a structure and
enough properties to choose a molecule. Chemistry search itself is delegated to
the provider (ChEMBL/PubChem maintain the indexes); this module does not build a
local fingerprint database.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from typing import Any
from urllib.parse import quote

import httpx

from vinastudio.core.errors import ExternalServiceError, InvalidInputError
from vinastudio.schemas.compound_library import CompoundHit, CompoundSearchPage

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_MAX_SDF_BYTES = 5 * 1024 * 1024
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
_CHEMBL_ID_RE = re.compile(r"^CHEMBL\d+$", re.IGNORECASE)
_CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
_PUBCHEM_PROPERTIES = (
    "Title,MolecularFormula,MolecularWeight,SMILES,InChIKey,"
    "HBondDonorCount,HBondAcceptorCount,RotatableBondCount,XLogP,TPSA,ConformerCount3D"
)

# Test seam: the suite injects a MockTransport so it never dials the network.
_TRANSPORT: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Replace the HTTP transport (tests only; ``None`` restores real HTTP)."""
    global _TRANSPORT
    _TRANSPORT = transport


class _RateWindow:
    """Small async sliding-window limiter shared by provider requests."""

    def __init__(self, count: int, seconds: float) -> None:
        self._count = count
        self._seconds = seconds
        self._times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self._seconds:
                    self._times.popleft()
                if len(self._times) < self._count:
                    self._times.append(now)
                    return
                await asyncio.sleep(max(self._seconds - (now - self._times[0]), 0.001))


_PUBCHEM_RATE = _RateWindow(5, 1.0)
_CHEMBL_RATE = _RateWindow(2, 1.0)


def _client() -> httpx.AsyncClient:
    kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "follow_redirects": True}
    if _TRANSPORT is not None:
        kwargs["transport"] = _TRANSPORT
    return httpx.AsyncClient(**kwargs)


async def _request(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    limiter: _RateWindow,
    service: str,
) -> httpx.Response:
    await limiter.wait()
    try:
        response = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise ExternalServiceError(f"{service} 不可达：{exc}") from exc
    if response.status_code == 429:
        raise ExternalServiceError(f"{service} 请求过于频繁，请稍后重试")
    if response.status_code >= 500:
        raise ExternalServiceError(f"{service} 服务异常（HTTP {response.status_code}）")
    return response


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_structure_query(query: str, mode: str) -> str:
    """Validate and canonicalise a SMILES query for chemical search."""
    if mode == "text":
        return query.strip()
    from rdkit import Chem

    mol = Chem.MolFromSmiles(query)
    if mol is None:
        raise InvalidInputError(
            f"{mode} search needs a valid SMILES, not {query!r}"
        )
    return Chem.MolToSmiles(mol, canonical=True)


class CompoundSource:
    id: str
    label: str
    license: str

    async def search(
        self,
        query: str,
        mode: str,
        limit: int,
        offset: int,
        threshold: int,
    ) -> CompoundSearchPage:
        raise NotImplementedError

    async def fetch(self, source_id: str) -> tuple[bytes, bool]:
        raise NotImplementedError


class PubChemSource(CompoundSource):
    id = "pubchem"
    label = "PubChem"
    license = "PubChem public data (NCBI/NLM); anonymous limit 5 requests/s"

    @staticmethod
    def _source_url(cid: str) -> str:
        return f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"

    async def _cids(self, client: httpx.AsyncClient, query: str, mode: str, threshold: int) -> list[int]:
        if mode == "similarity":
            url = f"{_PUBCHEM_BASE}/fastsimilarity_2d/smiles/{quote(query, safe='')}/cids/JSON"
            response = await _request(
                client,
                url,
                params={"Threshold": threshold, "MaxRecords": 200},
                limiter=_PUBCHEM_RATE,
                service=self.label,
            )
        elif mode == "substructure":
            url = f"{_PUBCHEM_BASE}/fastsubstructure/smiles/{quote(query, safe='')}/cids/JSON"
            response = await _request(
                client,
                url,
                params={"MaxRecords": 200},
                limiter=_PUBCHEM_RATE,
                service=self.label,
            )
        else:
            text = query.strip()
            if text.isdigit():
                return [int(text)]
            if _INCHIKEY_RE.match(text.upper()):
                url = f"{_PUBCHEM_BASE}/inchikey/{quote(text.upper(), safe='')}/cids/JSON"
                response = await _request(
                    client, url, limiter=_PUBCHEM_RATE, service=self.label
                )
            else:
                url = f"{_PUBCHEM_BASE}/name/{quote(text, safe='')}/cids/JSON"
                response = await _request(
                    client, url, limiter=_PUBCHEM_RATE, service=self.label
                )
        if response.status_code in (400, 404):
            return []
        if response.status_code != 200:
            raise ExternalServiceError(
                f"{self.label} 服务异常（HTTP {response.status_code}）"
            )
        try:
            identifier = response.json()["IdentifierList"]
            raw = identifier.get("CID") or identifier.get("cid")
            return [int(cid) for cid in raw]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ExternalServiceError("PubChem 返回了非预期的检索结果") from exc

    async def _properties(
        self, client: httpx.AsyncClient, cids: list[int]
    ) -> dict[int, dict[str, Any]]:
        if not cids:
            return {}
        url = f"{_PUBCHEM_BASE}/cid/{','.join(str(c) for c in cids)}/property/{_PUBCHEM_PROPERTIES}/JSON"
        response = await _request(
            client, url, limiter=_PUBCHEM_RATE, service=self.label
        )
        if response.status_code != 200:
            return {}
        try:
            rows = response.json()["PropertyTable"]["Properties"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExternalServiceError("PubChem 返回了非预期的性质数据") from exc
        return {int(row["CID"]): row for row in rows if "CID" in row}

    async def search(
        self, query: str, mode: str, limit: int, offset: int, threshold: int
    ) -> CompoundSearchPage:
        query = _valid_structure_query(query, mode)
        async with _client() as client:
            cids = await self._cids(client, query, mode, threshold)
            page_cids = cids[offset : offset + limit]
            properties = await self._properties(client, page_cids)

        results = []
        for cid in page_cids:
            row = properties.get(cid, {})
            results.append(
                CompoundHit(
                    source=self.id,
                    id=str(cid),
                    name=str(row.get("Title") or f"CID {cid}"),
                    formula=row.get("MolecularFormula"),
                    molecularWeight=_number(row.get("MolecularWeight")),
                    smiles=row.get("SMILES") or row.get("ConnectivitySMILES"),
                    inchiKey=row.get("InChIKey"),
                    score=None,
                    has3D=bool(_number(row.get("ConformerCount3D")) or 0),
                    license=self.license,
                    sourceUrl=self._source_url(str(cid)),
                    properties={
                        key: row[key]
                        for key in (
                            "HBondDonorCount",
                            "HBondAcceptorCount",
                            "RotatableBondCount",
                            "XLogP",
                            "TPSA",
                        )
                        if key in row
                    },
                )
            )
        return CompoundSearchPage(
            source=self.id,
            mode=mode,  # type: ignore[arg-type]
            total=len(cids),
            offset=offset,
            limit=limit,
            results=results,
        )

    async def fetch(self, source_id: str) -> tuple[bytes, bool]:
        if not source_id.isdigit():
            raise InvalidInputError(f"invalid PubChem CID: {source_id}")
        url = f"{_PUBCHEM_BASE}/cid/{source_id}/SDF"
        async with _client() as client:
            response = await _request(
                client,
                url,
                params={"record_type": "3d"},
                limiter=_PUBCHEM_RATE,
                service=self.label,
            )
        if response.status_code == 404:
            raise InvalidInputError("该 PubChem 条目没有 3D 构象")
        if response.status_code != 200:
            raise ExternalServiceError(
                f"{self.label} 下载失败（HTTP {response.status_code}）"
            )
        content = response.content
        if len(content) > _MAX_SDF_BYTES:
            raise ExternalServiceError("PubChem 返回的 SDF 过大")
        if b"M  END" not in content:
            raise ExternalServiceError("PubChem 返回的不是 SDF")
        return content, True


class ChEMBLSource(CompoundSource):
    id = "chembl"
    label = "ChEMBL"
    license = "ChEMBL data, CC BY-SA 3.0; cite https://www.ebi.ac.uk/chembl"

    @staticmethod
    def _source_url(chembl_id: str) -> str:
        return f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/"

    @staticmethod
    def _hit(raw: dict[str, Any]) -> CompoundHit:
        properties = raw.get("molecule_properties") or {}
        structures = raw.get("molecule_structures") or {}
        chembl_id = str(raw.get("molecule_chembl_id") or "")
        return CompoundHit(
            source="chembl",
            id=chembl_id,
            name=str(raw.get("pref_name") or chembl_id),
            formula=properties.get("full_molformula"),
            molecularWeight=_number(properties.get("full_mwt")),
            smiles=structures.get("canonical_smiles"),
            inchiKey=structures.get("standard_inchi_key"),
            score=_number(raw.get("score")),
            # The public ChEMBL SDF endpoint currently writes a 2D molfile.
            has3D=False,
            license=ChEMBLSource.license,
            sourceUrl=ChEMBLSource._source_url(chembl_id),
            properties={
                key: properties[key]
                for key in (
                    "hba",
                    "hbd",
                    "rtb",
                    "psa",
                    "alogp",
                    "qed_weighted",
                    "num_ro5_violations",
                )
                if key in properties
            },
        )

    async def search(
        self, query: str, mode: str, limit: int, offset: int, threshold: int
    ) -> CompoundSearchPage:
        query = _valid_structure_query(query, mode)
        async with _client() as client:
            if mode == "text" and _CHEMBL_ID_RE.match(query):
                url = f"{_CHEMBL_BASE}/molecule/{quote(query.upper(), safe='')}.json"
                response = await _request(
                    client, url, limiter=_CHEMBL_RATE, service=self.label
                )
                if response.status_code == 404:
                    return CompoundSearchPage(
                        source=self.id, mode=mode, total=0, offset=offset, limit=limit, results=[]
                    )
                if response.status_code != 200:
                    raise ExternalServiceError(
                        f"{self.label} 服务异常（HTTP {response.status_code}）"
                    )
                raw = response.json()
                molecules = [raw] if raw.get("molecule_chembl_id") else []
                total = len(molecules)
            else:
                if mode == "similarity":
                    url = (
                        f"{_CHEMBL_BASE}/similarity/"
                        f"{quote(query, safe='')}/{threshold}.json"
                    )
                elif mode == "substructure":
                    url = f"{_CHEMBL_BASE}/substructure/{quote(query, safe='')}.json"
                else:
                    url = f"{_CHEMBL_BASE}/molecule/search.json"
                params = {"limit": limit, "offset": offset}
                if mode == "text":
                    params["q"] = query
                response = await _request(
                    client, url, params=params, limiter=_CHEMBL_RATE, service=self.label
                )
                if response.status_code in (400, 404):
                    return CompoundSearchPage(
                        source=self.id, mode=mode, total=0, offset=offset, limit=limit, results=[]
                    )
                if response.status_code != 200:
                    raise ExternalServiceError(
                        f"{self.label} 服务异常（HTTP {response.status_code}）"
                    )
                payload = response.json()
                molecules = payload.get("molecules") or []
                total = int((payload.get("page_meta") or {}).get("total_count") or 0)

        warnings = []
        if any(not hit.has3D for hit in (self._hit(raw) for raw in molecules)):
            warnings.append("ChEMBL 返回 2D 结构；加入后请用准备流程生成 3D。")
        return CompoundSearchPage(
            source=self.id,
            mode=mode,  # type: ignore[arg-type]
            total=total,
            offset=offset,
            limit=limit,
            results=[self._hit(raw) for raw in molecules],
            warnings=warnings,
        )

    async def fetch(self, source_id: str) -> tuple[bytes, bool]:
        if not _CHEMBL_ID_RE.match(source_id):
            raise InvalidInputError(f"invalid ChEMBL ID: {source_id}")
        url = f"{_CHEMBL_BASE}/molecule/{quote(source_id.upper(), safe='')}.sdf"
        async with _client() as client:
            response = await _request(
                client, url, limiter=_CHEMBL_RATE, service=self.label
            )
        if response.status_code == 404:
            raise InvalidInputError(f"ChEMBL 未找到 {source_id}")
        if response.status_code != 200:
            raise ExternalServiceError(
                f"{self.label} 下载失败（HTTP {response.status_code}）"
            )
        content = response.content
        if len(content) > _MAX_SDF_BYTES:
            raise ExternalServiceError("ChEMBL 返回的 SDF 过大")
        if b"M  END" not in content:
            raise ExternalServiceError("ChEMBL 返回的不是 SDF")
        # ChEMBL's current public SDF endpoint writes a 2D molfile.
        return content, False


SOURCES: dict[str, CompoundSource] = {
    "pubchem": PubChemSource(),
    "chembl": ChEMBLSource(),
}


def source_info() -> list[dict[str, Any]]:
    return [
        {
            "id": source.id,
            "label": source.label,
            "license": source.license,
            "capabilities": ["text", "similarity", "substructure"],
            "note": (
                "PubChem exposes 3D conformers."
                if source.id == "pubchem"
                else "ChEMBL structures may be 2D until prepared."
            ),
        }
        for source in SOURCES.values()
    ]
