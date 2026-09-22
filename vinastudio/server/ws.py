"""WebSocket fan-out used to stream job progress and logs to the interface."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter()


class EventHub:
    """Broadcast JSON events to every connected interface.

    Docking workers run in child processes, so events may arrive from a worker
    thread. :meth:`publish_threadsafe` bridges that case onto the server loop.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server loop so worker threads can publish onto it."""
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        log.debug("event client connected (%d total)", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        log.debug("event client disconnected (%d left)", len(self._clients))

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        if not targets:
            return
        results = await asyncio.gather(
            *(ws.send_json(event) for ws in targets), return_exceptions=True
        )
        for websocket, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                await self.disconnect(websocket)

    def publish_threadsafe(self, event: dict[str, Any]) -> None:
        """Publish from a non-async thread (job workers, Qt callbacks)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            log.debug("dropping event without an active loop: %s", event.get("type"))
            return
        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)

    @property
    def client_count(self) -> int:
        return len(self._clients)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Keep a duplex channel open; job events flow server to client."""
    hub: EventHub = websocket.app.state.events
    await hub.connect(websocket)
    try:
        await websocket.send_json({"type": "hello", "clients": hub.client_count})
        while True:
            # Inbound messages are keep-alives / future commands; echoing them
            # back lets the frontend verify the channel cheaply.
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        log.exception("websocket error")
    finally:
        await hub.disconnect(websocket)
