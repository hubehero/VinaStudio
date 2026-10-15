"""Which origins may drive this API.

The API is a local backend: the desktop shell loads it from loopback and nothing
else is meant to reach it. Browsers attach ``Origin`` to every state-changing
request, so one that carries a *foreign* origin came from a page the user is
merely visiting — the local-server CSRF shape, where a page can POST to
``127.0.0.1`` without being able to read the answer. Most of our write endpoints
take a JSON body, which makes the browser preflight them and drop them without
CORS headers; the guard covers the rest, and makes the policy explicit.

Two rules, both deliberate:

* **A request with no ``Origin`` is allowed.** That is curl, a script, a test
  client, or a same-origin navigation — none of them something a browser adds by
  accident, so treating "absent" as hostile would break the tooling for nothing.
* **``Origin: null`` is treated as foreign.** A sandboxed iframe or a ``file://``
  page sends it, and our own client never does.
"""

from __future__ import annotations

from collections.abc import Collection
from urllib.parse import urlsplit

#: Methods a browser can use to cause a side effect. GET/HEAD/OPTIONS are reads
#: and stay unguarded — guarding those would break plain links and image loads
#: for no security gain.
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Loopback only, any port: the packaged app is served from a kernel-assigned
#: one, so the port cannot be part of the rule. A page on a remote site has an
#: origin like ``https://example.com`` and never matches.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Origins the Vite dev server serves the interface from. The loopback rule
#: above already covers them; naming them keeps the dev setup explicit, and CORS
#: needs the list too. It lives here so ``ws.py`` can use it without importing
#: the application module (which imports ``ws``).
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def origin_is_trusted(origin: str | None, extra_origins: Collection[str] = ()) -> bool:
    """Whether *origin* may issue a state-changing request.

    ``extra_origins`` carries the Vite dev server when one is configured
    (``DEV_ORIGINS``); it is redundant with the loopback rule in practice and
    kept so the dev setup stays readable.
    """
    if not origin:
        return True
    if origin == "null":
        return False
    if origin in extra_origins:
        return True
    parts = urlsplit(origin)
    if parts.scheme not in {"http", "https"}:
        return False
    return (parts.hostname or "").lower() in LOOPBACK_HOSTS
