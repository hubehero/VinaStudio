"""Per-session authorization for the loopback API (H2).

The API is bound to loopback, but loopback is reachable by every local user and
process. A desktop-launched server therefore generates one random token per
process and requires it on every data-bearing route. The token never leaves
memory: the desktop shell injects it into the page, the page sends it back.
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlsplit

TOKEN_HEADER = "x-vinastudio-token"
WS_PROTOCOL_PREFIX = "vinastudio."
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def generate_token() -> str:
    """256 bits of randomness, URL-safe so it can also be a WS subprotocol."""
    return secrets.token_urlsafe(32)


def token_matches(expected: str, presented: str | None) -> bool:
    """Constant-time comparison; a missing value never matches."""
    return bool(presented) and secrets.compare_digest(expected, presented)


def host_is_trusted(host_header: str | None) -> bool:
    """Whether a ``Host`` header names loopback, with or without a port.

    DNS rebinding keeps the attacker's host name in ``Host`` while the socket
    already points at 127.0.0.1, so accepting only loopback names closes it.
    An IPv6 literal must be bracketed in ``Host``; an unbracketed value is
    ambiguous and is refused.
    """
    if not host_header:
        return False
    host = host_header.strip()
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return False
        host = host[1:end]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    elif host.count(":") > 1:
        return False
    return host.lower().rstrip(".") in LOOPBACK_HOSTS


def is_loopback_url(url: str) -> bool:
    """Whether the interface URL belongs to this machine.

    A developer can point ``--ui-url`` at anything. Injecting the token into a
    remote page would hand that page the API, so the caller must check first.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and (parts.hostname or "").lower() in LOOPBACK_HOSTS


def ws_subprotocol_token(protocols: list[str]) -> str | None:
    """Token carried by ``Sec-WebSocket-Protocol``, if one was offered."""
    for protocol in protocols:
        if protocol.startswith(WS_PROTOCOL_PREFIX):
            return protocol[len(WS_PROTOCOL_PREFIX) :]
    return None


def token_injection_script(token: str, url: str) -> str:
    """JavaScript that publishes the token only on the expected page origin.

    A ``QWebEngineScript`` at ``DocumentCreation`` runs on every main-frame
    navigation, including an external page the user reaches from a link. The
    origin check keeps the token out of that page; an external origin never
    matches, while the bundled build and the Vite dev server both do.
    """
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    return (
        "(() => {\n"
        f"  if (window.location.origin !== {json.dumps(origin)}) return;\n"
        f"  window.__VINASTUDIO_TOKEN__ = {json.dumps(token)};\n"
        "})();"
    )
