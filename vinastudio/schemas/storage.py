"""HTTP contract for job-storage accounting and explicit deletion."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobStorageEntry(BaseModel):
    jobId: str
    label: str = ""
    status: str
    createdAt: float = 0.0
    bytes: int = Field(ge=0)
    files: int = Field(ge=0)
    deletable: bool


class JobStorageSummary(BaseModel):
    count: int = Field(ge=0)
    totalBytes: int = Field(ge=0)
    deletableBytes: int = Field(ge=0)
    entries: list[JobStorageEntry] = Field(default_factory=list)


class DeletedJob(BaseModel):
    jobId: str
    bytes: int = Field(ge=0)
