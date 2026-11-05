"""Reject oversized request bodies before FastAPI parses them (H4).

`UploadFile.size` is trustworthy, but it is only known after the multipart
parser has already consumed and spooled the whole request. This middleware runs
before routing, checks the declared length, and counts the real bytes when a
client sends a chunked body without one.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    """Raised from the wrapped ``receive`` so the middleware can answer 413."""


class BodyLimitMiddleware:
    """Cap the total HTTP request body for every route.

    ``max_body_size`` is a callable so the configured limit is read per request
    (the environment variable can change in tests without rebuilding the app).
    """

    def __init__(self, app: ASGIApp, max_body_size: Callable[[], int]) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.max_body_size()
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            await _too_large(scope, receive, send)
            return

        total = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise _BodyTooLarge
            return message

        async def watched_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, watched_send)
        except _BodyTooLarge:
            # A streaming endpoint may have started its response before reading
            # the body; there is no safe 413 to send at that point.
            if response_started:
                raise
            await _too_large(scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name.lower() != b"content-length":
            continue
        try:
            length = int(value)
        except (TypeError, ValueError):
            return None
        return length if length >= 0 else None
    return None


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse(
        status_code=413,
        content={"detail": "request body exceeds the upload limit"},
    )
    await response(scope, receive, send)
