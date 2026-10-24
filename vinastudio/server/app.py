"""FastAPI application factory for the loopback API + bundled interface."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from os import PathLike
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from vinastudio import __version__
from vinastudio.config import APP_NAME, STATIC_DIR, dev_server_url
from vinastudio.core.errors import ReceptorTemplateError, VinaStudioError
from vinastudio.core.paths import resolve_artifact
from vinastudio.server.job_manager import manager as job_manager
from vinastudio.server.origin import (
    DEV_ORIGINS,
    STATE_CHANGING_METHODS,
    origin_is_trusted,
)
from vinastudio.server.routers import (
    box,
    chem,
    docking,
    files,
    interactions,
    library,
    library_compounds,
    ligand,
    molecules,
    project,
    receptor,
    results,
    screening,
    sites,
    system,
    workspace,
)
from vinastudio.server.ws import EventHub
from vinastudio.server.ws import router as ws_router

log = logging.getLogger(__name__)

# The origin policy (which callers may drive the API, and why a missing Origin is
# allowed) lives in `server/origin.py`; `DEV_ORIGINS` comes from there so `ws.py`
# can share it without a circular import.


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.events.bind_loop(asyncio.get_running_loop())
    job_manager.bind_hub(app.state.events)
    # Rebuild the jobs list from job.json so a restarted session still shows
    # past results; never in JobManager.__init__ — imports must not do IO.
    job_manager.restore_history()
    log.info("%s API ready", APP_NAME)
    yield
    job_manager.shutdown()
    log.info("%s API shutting down", APP_NAME)


def create_app() -> FastAPI:
    """Build the application. Called once by the desktop shell."""
    app = FastAPI(
        title=f"{APP_NAME} API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.state.events = EventHub()
    app.state.started_at = time.time()

    # The packaged interface is served from this same origin, so CORS is only
    # needed while a Vite dev server hosts it — and a credentialed wildcard is
    # not something to leave switched on for a shipped build.
    if dev_server_url() is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=DEV_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # A page the user is merely visiting must not be able to drive this API. The
    # desktop shell is the only client and it is same-origin, so anything that
    # announces a foreign origin is refused; see `server/origin.py` for why a
    # missing origin is allowed. Added last, so it runs before CORS.
    @app.middleware("http")
    async def _reject_foreign_origins(request: Request, call_next: Any) -> Any:
        if request.method in STATE_CHANGING_METHODS and not origin_is_trusted(
            request.headers.get("origin"), DEV_ORIGINS
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "this API is local: a request from another origin is refused"},
            )
        return await call_next(request)

    # WebSocket channel sits at the root so the frontend has a stable URL.
    app.include_router(ws_router)

    # Domain routers; each new phase adds one here.
    for router in (system.router, files.router, ligand.router, receptor.router, box.router, docking.router, project.router, interactions.router, workspace.router, library.router, library_compounds.router, molecules.router, chem.router, results.router, screening.router, sites.router):
        app.include_router(router, prefix="/api")

    _add_docs_endpoint(app)
    _add_domain_error_handler(app)
    _mount_artifacts(app)
    _mount_interface(app)
    return app


def _add_docs_endpoint(app: FastAPI) -> None:
    """Serve Swagger UI from locally-bundled assets (no CDN dependency)."""

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html() -> HTMLResponse:
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html>
<head>
<link rel="stylesheet" href="/swagger/swagger-ui.css">
<title>{APP_NAME} API Docs</title>
</head>
<body>
<div id="swagger-ui"></div>
<script src="/swagger/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({{
  url: "/api/openapi.json",
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
  layout: "BaseLayout"
}});
</script>
</body>
</html>"""
        )


def _add_domain_error_handler(app: FastAPI) -> None:
    """Map domain errors onto status codes once, instead of per endpoint."""

    @app.exception_handler(VinaStudioError)
    async def _handle(_request: Request, error: VinaStudioError) -> JSONResponse:
        payload: dict[str, object] = {"detail": str(error), "kind": type(error).__name__}
        if isinstance(error, ReceptorTemplateError) and error.residues:
            # The interface offers to exclude these and retry, so they have to
            # travel structurally rather than only inside the message.
            payload["residues"] = list(error.residues)
        if error.status_code >= 500:
            log.exception("unhandled domain error: %s", error)
        return JSONResponse(status_code=error.status_code, content=payload)


def _mount_artifacts(app: FastAPI) -> None:
    """Serve prepared files so the renderer can fetch them by URL.

    Uses a dynamic endpoint instead of ``StaticFiles`` so that workspace
    changes at runtime (init / set / migrate) are picked up immediately
    without restarting the server.
    """

    @app.get("/artifacts/{path:path}")
    async def serve_artifact(path: str) -> FileResponse:
        try:
            resolved = resolve_artifact(path)
        except ValueError:
            raise HTTPException(status_code=404, detail="artifact not found") from None
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        media_type, _ = mimetypes.guess_type(str(resolved))
        return FileResponse(str(resolved), media_type=media_type)


class _InterfaceStaticFiles(StaticFiles):
    """Static server with the cache policy the desktop shell depends on.

    ``StaticFiles`` sends validators but no ``Cache-Control``, so Chromium
    falls back to heuristic freshness. The shell's persistent QWebEngine
    profile keeps a disk cache across restarts, which means a rebuilt
    ``index.html`` could be skipped entirely and the window would silently
    run the previous bundle — the stale hashed assets are still on disk, so
    nothing fails loudly. HTML must revalidate on every load; content-hashed
    ``assets/`` files are immutable by name and safe to pin.
    """

    def file_response(  # type: ignore[override]
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(
            full_path, stat_result, scope, status_code=status_code
        )
        # The mount prefix may or may not be stripped from scope["path"]
        # depending on Starlette's routing, so compare the relative form.
        path = scope.get("path", "").lstrip("/")
        if path.startswith("assets/"):
            response.headers["cache-control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers["cache-control"] = "no-cache"
        return response


def _mount_interface(app: FastAPI) -> None:
    """Serve the built SPA, or explain how to produce it."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        # Mounted last so the API routes above win the match.
        app.mount("/", _InterfaceStaticFiles(directory=STATIC_DIR, html=True), name="ui")
        return

    log.warning("Interface bundle missing at %s", STATIC_DIR)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def missing_interface() -> HTMLResponse:
        dev = dev_server_url()
        hint = (
            f'<p>开发服务器：<code>VINASTUDIO_DEV_SERVER_URL={dev}</code></p>'
            if dev
            else "<p>构建界面：<code>uv run python scripts/build_web.py</code></p>"
        )
        return HTMLResponse(
            f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{APP_NAME}</title>
<style>
 :root {{ color-scheme: dark; }}
 body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#0d1526;
        color:#e6edf7; font:15px/1.7 -apple-system,"Segoe UI","Noto Sans SC",sans-serif; }}
 .card {{ max-width:620px; padding:38px 42px; border-radius:16px; background:#151f36;
         border:1px solid #24314f; }}
 h1 {{ font-size:19px; margin:0 0 14px; color:#4fd1c5; }}
 code {{ background:#0a1120; padding:3px 7px; border-radius:6px; color:#9fd3ff; }}
</style></head><body><div class="card">
 <h1>界面构建产物缺失 / Interface bundle missing</h1>
 {hint}
 <p>API 文档 / API docs: <code><a style="color:#9fd3ff" href="/docs">/docs</a></code></p>
</div></body></html>"""
        )
