"""Run the FastAPI application on a background thread inside the Qt process."""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI

log = logging.getLogger(__name__)


class _PortReportingServer(uvicorn.Server):
    """Uvicorn server that announces the port it actually bound to."""

    def __init__(self, config: uvicorn.Config, on_bound: Callable[[int], None]) -> None:
        super().__init__(config)
        self._on_bound = on_bound

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:  # type: ignore[override]
        await super().startup(sockets)
        for server in self.servers:
            for sock in server.sockets or ():
                try:
                    self._on_bound(sock.getsockname()[1])
                except (OSError, IndexError, TypeError):  # pragma: no cover - defensive
                    continue


class LocalServer:
    """Owns the lifespan of the loopback-only API server.

    Uvicorn runs on a dedicated thread with its own event loop while Qt keeps
    the main thread. Blocking docking work never touches this loop: it is
    dispatched to spawned worker processes.
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        log_level: str = "info",
    ) -> None:
        self._config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=False,
            # The desktop shell owns signals; uvicorn must not install handlers
            # from a non-main thread.
            lifespan="on",
        )
        self._bound = threading.Event()
        self._port: int | None = None
        self._thread: threading.Thread | None = None
        self._server = _PortReportingServer(self._config, self._on_bound)

    # -- lifecycle ---------------------------------------------------------
    def start(self, timeout: float = 20.0) -> int:
        """Start the server and block until it is accepting connections."""
        if self._thread is not None:
            raise RuntimeError("server already started")

        self._thread = threading.Thread(target=self._server.run, name="vinastudio-api", daemon=True)
        self._thread.start()

        if not self._bound.wait(timeout):
            self.stop()
            raise TimeoutError(f"API server did not start within {timeout:.0f}s")
        assert self._port is not None
        log.info("API server listening on http://%s:%d", self._config.host, self._port)
        return self._port

    def stop(self, timeout: float = 10.0) -> None:
        """Ask uvicorn to shut down and wait for its thread to finish."""
        self._server.should_exit = True
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            if thread.is_alive():  # pragma: no cover - defensive
                log.warning("API server thread did not stop within %.0fs", timeout)

    # -- accessors ---------------------------------------------------------
    @property
    def port(self) -> int | None:
        return self._port

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("server is not running")
        return f"http://{self._config.host}:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _on_bound(self, port: int) -> None:
        self._port = port
        self._bound.set()
