"""CORS is a development affordance, not something a shipped build needs.

The packaged interface is served from the API's own origin, so the only reason
to allow a different one is the Vite dev server — and the middleware that was
installed unconditionally also allowed credentials.
"""

from __future__ import annotations

from pathlib import Path

from vinastudio.config import DEV_SERVER_ENV


def _middleware_names(monkeypatch, home: Path) -> list[str]:  # type: ignore[no-untyped-def]
    from vinastudio.server.app import create_app

    monkeypatch.setenv("VINASTUDIO_HOME", str(home))
    return [middleware.cls.__name__ for middleware in create_app().user_middleware]


def test_cors_is_absent_without_a_dev_server(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(DEV_SERVER_ENV, raising=False)

    assert "CORSMiddleware" not in _middleware_names(monkeypatch, tmp_path)


def test_cors_is_installed_for_the_dev_server(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(DEV_SERVER_ENV, "http://127.0.0.1:5173")

    assert "CORSMiddleware" in _middleware_names(monkeypatch, tmp_path)
