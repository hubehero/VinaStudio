"""Wire models for the workspace molecule catalog."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vinastudio.schemas.preparation import LigandOptions, ReceptorOptions


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class _CatalogModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="ignore")


class MoleculeFileOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    kind: str
    path: str
    path_kind: str = "workspace"
    sha256: str | None = None
    bytes: int = 0
    is_primary: bool = False


class CatalogMoleculeOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    kind_hint: str
    source: str = ""
    source_id: str = ""
    identity_key: str
    identity_kind: str
    canonical_smiles: str | None = None
    inchi_key: str | None = None
    parent_inchi_key: str | None = None
    formula: str | None = None
    molecular_weight: float | None = None
    qed: float | None = None
    lipinski_violations: int | None = None
    tpsa: float | None = None
    clogp: float | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None
    descriptor_version: str | None = None
    status: str = "active"
    prep_status: str = "unknown"
    primary_path: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    files: list[MoleculeFileOut] = Field(default_factory=list)
    studies: list[dict[str, Any]] = Field(default_factory=list)
    collections: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CatalogSearchOut(_CatalogModel):
    items: list[CatalogMoleculeOut]
    total: int
    limit: int
    offset: int
    facets: dict[str, list[dict[str, Any]]]


class SelectionSpec(_CatalogModel):
    """A replayable catalog query; UI filters map to ``filters``."""

    q: str = ""
    filters: dict[str, list[str]] = Field(default_factory=dict)
    maxMembers: int = Field(default=50000, ge=1, le=50000)


class SelectionCreate(_CatalogModel):
    name: str = ""
    source: str = "query"
    spec: SelectionSpec = Field(default_factory=SelectionSpec)
    moleculeIds: list[str] = Field(default_factory=list)


class SelectionMemberOut(_CatalogModel):
    entry_index: int
    identity_key: str
    id: str
    name: str
    kind_hint: str
    prep_status: str = "unknown"
    molecular_weight: float | None = None
    qed: float | None = None
    lipinski_violations: int | None = None
    tpsa: float | None = None
    clogp: float | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None


class SelectionOut(_CatalogModel):
    id: str
    name: str
    source: str
    spec: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    resolved_at: float | None = None
    member_count: int = 0
    prepared_count: int = 0
    truncated: bool = False
    schema_version: int = 1
    members: list[SelectionMemberOut] = Field(default_factory=list)
    total: int = 0


class CollectionMemberOut(_CatalogModel):
    id: str
    name: str
    kind_hint: str
    prep_status: str = "unknown"


class CollectionOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    parent_id: str | None = None
    name: str
    description: str = ""
    color: str | None = None
    sort_order: int = 0
    kind: str = "manual"
    query: dict[str, Any] = Field(default_factory=dict)
    molecule_count: int = 0
    members: list[CollectionMemberOut] = Field(default_factory=list)


class StudyMemberOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    kind_hint: str
    prep_status: str = "unknown"
    role: Literal["receptor", "ligand", "cofactor"] | str
    is_primary: bool = False
    canonical_smiles: str | None = None


class StudyOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: str = ""
    source: str = ""
    pdb_id: str | None = None
    receptor_count: int = 0
    ligand_count: int = 0
    members: list[StudyMemberOut] = Field(default_factory=list)


class LibraryMemberOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    entry_index: int
    prepared_path: str | None = None
    id: str
    name: str
    kind_hint: str
    prep_status: str = "unknown"
    canonical_smiles: str | None = None


class LibraryOut(_CatalogModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: str = ""
    source: str = ""
    molecule_count: int = 0
    prepared_count: int = 0
    members: list[LibraryMemberOut] = Field(default_factory=list)


class SuggestionOut(_CatalogModel):
    id: str
    kind: str
    title: str
    reason: str
    confidence: float
    moleculeIds: list[str]
    payload: dict[str, Any] = Field(default_factory=dict)


class SavedViewOut(_CatalogModel):
    id: str
    name: str
    scope: str
    query: dict[str, Any] = Field(default_factory=dict)
    createdAt: float


class SavedViewCreate(_CatalogModel):
    name: str = Field(min_length=1, max_length=80)
    query: dict[str, Any] = Field(default_factory=dict)


class CatalogPrepareRequest(_CatalogModel):
    receptorOptions: ReceptorOptions | None = None
    ligandOptions: LigandOptions | None = None


class ImportRequest(_CatalogModel):
    paths: list[str] = Field(min_length=1)
    kindHint: Literal["receptor", "ligand", "unknown"] = "unknown"


class CollectionCreate(_CatalogModel):
    name: str = Field(min_length=1, max_length=200)
    parentId: str | None = None
    description: str = ""
    color: str | None = None
    kind: Literal["manual", "smart"] = "manual"
    query: dict[str, Any] = Field(default_factory=dict)


class CollectionPatch(_CatalogModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    parentId: str | None = None
    sortOrder: int | None = None
    query: dict[str, Any] | None = None


class StudyCreate(_CatalogModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    source: str = ""
    pdbId: str | None = None


class StudyPatch(_CatalogModel):
    name: str | None = None
    description: str | None = None
    pdbId: str | None = None


class StudyMemberAdd(_CatalogModel):
    moleculeId: str
    role: Literal["receptor", "ligand", "cofactor"]
    isPrimary: bool = False


class LibraryCreate(_CatalogModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    moleculeIds: list[str] = Field(default_factory=list)
    selectionId: str | None = None


class LibraryMemberAdd(_CatalogModel):
    moleculeId: str
    entryIndex: int | None = None
    preparedPath: str | None = None
