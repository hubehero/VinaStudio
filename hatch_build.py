"""Build guard: refuse a wheel without the compiled interface.

The SPA is produced by ``scripts/build_web.py`` (or ``pnpm build``) into a
gitignored directory, and ``pyproject.toml`` force-includes that directory.
Without this guard a fresh checkout gets hatchling's raw missing-directory
error, while an empty directory would silently produce an unusable wheel.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def require_frontend_assets(root: str | Path) -> None:
    """Raise a user-facing error unless the built SPA is present."""
    index = Path(root) / "vinastudio" / "server" / "static" / "index.html"
    if index.is_file() and index.stat().st_size > 0:
        return
    raise RuntimeError(
        "the web interface has not been built; refusing to create a wheel "
        "without vinastudio/server/static/index.html.\n"
        "Run: pnpm -C web install && pnpm -C web build\n"
        "or:  uv run python scripts/build_web.py"
    )


class FrontendAssetsRequired(BuildHookInterface):
    """Hatch wheel hook that runs :func:`require_frontend_assets`."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        require_frontend_assets(self.root)
