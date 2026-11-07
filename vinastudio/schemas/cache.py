"""HTTP contract for the local preparation cache."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CacheSettings(BaseModel):
    """User-visible cache policy; defaults match the conservative startup rule."""

    autoCleanup: bool = True
    retentionDays: int = Field(default=30, ge=0, le=3650)
    maxEntries: int = Field(default=100, ge=1, le=100000)


class CacheSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autoCleanup: bool
    retentionDays: int = Field(ge=0, le=3650)
    maxEntries: int = Field(ge=1, le=100000)


class CacheStats(BaseModel):
    entries: int = Field(ge=0)
    bytes: int = Field(ge=0)
    protectedEntries: int = Field(ge=0)
    protectedBytes: int = Field(ge=0)
    oldestDays: float | None = None


class CacheState(BaseModel):
    settings: CacheSettings
    stats: CacheStats


class CacheClearResult(BaseModel):
    removed: int = Field(ge=0)
    bytes: int = Field(ge=0)
    skippedProtected: int = Field(ge=0)
