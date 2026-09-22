"""FastAPI application factory for the loopback API + bundled interface."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from vinastudio import __version__
from vinastudio.config import APP_NAME, STATIC_DIR, dev_server_url
from vinastudio.core.errors import ReceptorTemplateError, VinaStudioError
from vinastudio.server.job_manager import manager as job_manager
from vinastudio.server.routers import (
    box,
    docking,
    files,
    interactions,
    library,
    ligand,
    project,
    receptor,
    system,
    workspace,
)
from vinastudio.server.ws import EventHub
from vinastudio.server.ws import router as ws_router

log = logging.getLogger(__name__)

#: Origins allowed to call the API. Production is same-origin; the Vite dev
#: server needs to be listed explicitly so hot reload keeps working.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.events.bind_loop(asyncio.get_running_loop())
    job_manager.bind_hub(app.state.events)
    log.info("%s API ready", APP_NAME)
    yield
    job_manager.shutdown()
    log.info("%s API shutting down", APP_NAME)


def create_app() -> FastAPI:
    """Build the application. Called once by the desktop shell."""
    app = FastAPI(
        title=f"{APP_NAME} API",
        version=__version__,
        docs_url="/api/docs",
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

    # WebSocket channel sits at the root so the frontend has a stable URL.
    app.include_router(ws_router)

    # Domain routers; each new phase adds one here.
    for router in (system.router, files.router, ligand.router, receptor.router, box.router, docking.router, project.router, interactions.router, workspace.router, library.router):
        app.include_router(router, prefix="/api")

    _add_domain_error_handler(app)
    _mount_artifacts(app)
    _mount_interface(app)
    return app


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
    import mimetypes

    from fastapi.responses import FileResponse

    from vinastudio.core.paths import resolve_artifact

    @app.get("/artifacts/{path:path}")
    async def serve_artifact(path: str) -> FileResponse:
        try:
            resolved = resolve_artifact(path)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="artifact not found") from None
        if not resolved.is_file():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="artifact not found")
        media_type, _ = mimetypes.guess_type(str(resolved))
        return FileResponse(str(resolved), media_type=media_type)


def _mount_interface(app: FastAPI) -> None:
    """Serve the built SPA, or explain how to produce it."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        # Mounted last so the API routes above win the match.
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
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
 <p>API 文档 / API docs: <code><a style="color:#9fd3ff" href="/api/docs">/api/docs</a></code></p>
</div></body></html>"""
        )
