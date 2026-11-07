"""Local preparation-cache settings, statistics and explicit cleanup."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from vinastudio.core import prep_cache
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.paths import workspace_root
from vinastudio.core.workspace import referenced_workspace_dirs
from vinastudio.schemas.cache import (
    CacheClearResult,
    CacheSettings,
    CacheSettingsUpdate,
    CacheState,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/cache", tags=["cache"])


def _core_settings(value: CacheSettings) -> prep_cache.CacheSettings:
    return prep_cache.CacheSettings(
        auto_cleanup=value.autoCleanup,
        retention_days=value.retentionDays,
        max_entries=value.maxEntries,
    )


def _state() -> CacheState:
    try:
        protected = referenced_workspace_dirs(workspace_root())
    except ValueError as exc:
        # Fail closed: an unreadable reference source must not produce a
        # misleading deletable view or a cleanup that could remove live data.
        raise InvalidInputError(str(exc)) from None
    stats = prep_cache.cache_stats(protected=protected)
    settings = prep_cache.load_settings()
    return CacheState(
        settings=CacheSettings(
            autoCleanup=settings.auto_cleanup,
            retentionDays=settings.retention_days,
            maxEntries=settings.max_entries,
        ),
        stats=stats,
    )


@router.get("", response_model=CacheState)
def get_cache_state() -> CacheState:
    """Return the workspace cache policy and current accounting."""
    return _state()


@router.put("/settings", response_model=CacheState)
def update_cache_settings(request: CacheSettingsUpdate) -> CacheState:
    """Persist cache policy; cleanup remains an explicit action or startup task."""
    prep_cache.save_settings(_core_settings(request))
    return _state()


@router.post("/clear", response_model=CacheClearResult)
def clear_cache() -> CacheClearResult:
    """Remove unprotected cache entries immediately; referenced outputs stay."""
    try:
        protected = referenced_workspace_dirs(workspace_root())
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from None
    result = prep_cache.cleanup(
        prep_cache.load_settings(),
        protected=protected,
        manual=True,
    )
    log.info("manual preparation-cache clear: %s", result)
    return CacheClearResult.model_validate(result)
