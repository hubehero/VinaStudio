"""WebSocket fan-out used to stream job progress and logs to the interface."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vinastudio.server.auth import (
    WS_PROTOCOL_PREFIX,
    host_is_trusted,
    token_matches,
    ws_subprotocol_token,
)
from vinastudio.server.origin import DEV_ORIGINS, origin_is_trusted

log = logging.getLogger(__name__)

router = APIRouter()

#: A slow or stalled page must not make the server hold an unbounded event
#: backlog. Overflow disconnects that client; it can reconnect and re-read state.
CLIENT_QUEUE_MAX = 256
MAX_CLIENTS = 32
SEND_TIMEOUT = 5.0


@dataclass(slots=True)
class _Client:
    websocket: WebSocket
    queue: asyncio.Queue[dict[str, Any]]
    task: asyncio.Task[None] | None = None


class EventHub:
    """Broadcast JSON events to every connected interface.

    Docking workers run in child processes, so events may arrive from a worker
    thread. :meth:`publish_threadsafe` bridges that case onto the server loop.
    Each client has its own bounded queue and sender task, so one stalled page
    cannot stall the fan-out or make the server accumulate events forever.
    """

    def __init__(self) -> None:
        self._clients: dict[WebSocket, _Client] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server loop so worker threads can publish onto it."""
        self._loop = loop

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None) -> bool:
        """Accept a client unless the connection cap is already reached."""
        async with self._lock:
            if len(self._clients) >= MAX_CLIENTS:
                return False
            await websocket.accept(subprotocol=subprotocol)
            client = _Client(websocket, asyncio.Queue(maxsize=CLIENT_QUEUE_MAX))
            self._clients[websocket] = client
        client.task = asyncio.create_task(self._sender(client))
        log.debug("event client connected (%d total)", len(self._clients))
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        await self._remove(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning(
                    "event client queue full; disconnecting (%d pending)",
                    client.queue.qsize(),
                )
                await self._remove(client.websocket)

    async def send_to(self, websocket: WebSocket, event: dict[str, Any]) -> bool:
        """Queue one event for a client; False means it is gone or overflowing."""
        async with self._lock:
            client = self._clients.get(websocket)
        if client is None:
            return False
        try:
            client.queue.put_nowait(event)
        except asyncio.QueueFull:
            await self._remove(websocket)
            return False
        return True

    def publish_threadsafe(self, event: dict[str, Any]) -> None:
        """Publish from a non-async thread (job workers, Qt callbacks)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            log.debug("dropping event without an active loop: %s", event.get("type"))
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)
        except RuntimeError:
            log.debug("event loop rejected broadcast: %s", event.get("type"))
            return
        future.add_done_callback(self._log_broadcast_failure)

    @staticmethod
    def _log_broadcast_failure(future: Any) -> None:
        if future.cancelled():
            return
        error = future.exception()
        if error is not None:
            log.warning("event broadcast failed: %s", error)

    async def _sender(self, client: _Client) -> None:
        try:
            while True:
                event = await client.queue.get()
                await asyncio.wait_for(
                    client.websocket.send_json(event), timeout=SEND_TIMEOUT
                )
        except asyncio.CancelledError:
            raise
        except (WebSocketDisconnect, TimeoutError, RuntimeError, OSError):
            pass
        finally:
            with contextlib.suppress(asyncio.CancelledError):
                await self._remove(client.websocket, cancel_task=False)
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await client.websocket.close()

    async def _remove(self, websocket: WebSocket, *, cancel_task: bool = True) -> None:
        async with self._lock:
            client = self._clients.pop(websocket, None)
        if client is None:
            return
        task = client.task
        if (
            cancel_task
            and task is not None
            and task is not asyncio.current_task()
        ):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        log.debug("event client disconnected (%d left)", len(self._clients))

    @property
    def client_count(self) -> int:
        return len(self._clients)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Keep a duplex channel open; job events flow server to client.

    A WebSocket handshake is not covered by CORS, so a page the user is visiting
    could otherwise open this channel and read the job event stream. The same
    origin rule as the HTTP guard applies (``server/origin.py``).
    """
    if not origin_is_trusted(websocket.headers.get("origin"), DEV_ORIGINS):
        await websocket.close(code=1008)  # policy violation, before accept()
        return

    expected = websocket.app.state.api_token
    chosen_protocol: str | None = None
    if expected is not None:
        if not host_is_trusted(websocket.headers.get("host")):
            await websocket.close(code=1008)
            return
        # Parse the handshake header rather than ASGI's ``subprotocols`` list:
        # test clients and some servers only populate one of the two.
        offered = [
            protocol.strip()
            for protocol in (websocket.headers.get("sec-websocket-protocol") or "").split(",")
            if protocol.strip()
        ]
        chosen_protocol = next(
            (protocol for protocol in offered if protocol.startswith(WS_PROTOCOL_PREFIX)),
            None,
        )
        if chosen_protocol is None or not token_matches(
            expected, ws_subprotocol_token(offered)
        ):
            await websocket.close(code=1008)
            return

    hub: EventHub = websocket.app.state.events
    if not await hub.connect(websocket, subprotocol=chosen_protocol):
        await websocket.close(code=1008)
        return
    try:
        await hub.send_to(websocket, {"type": "hello", "clients": hub.client_count})
        while True:
            # Inbound messages are keep-alives / future commands; echoing them
            # back lets the frontend verify the channel cheaply.
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await hub.send_to(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        log.exception("websocket error")
    finally:
        await hub.disconnect(websocket)
