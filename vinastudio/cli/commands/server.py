"""``server``: run the local FastAPI app without the desktop shell."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "server", help="run the local API server (FastAPI) without Qt"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--token",
        default=None,
        help="API token; defaults to VINASTUDIO_API_TOKEN or a generated token",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    from vinastudio.server.app import create_app
    from vinastudio.server.auth import generate_token

    supplied = args.token or os.environ.get("VINASTUDIO_API_TOKEN")
    token = supplied or generate_token()
    if supplied is None:
        print(f"API token: {token}", file=sys.stderr)
    import uvicorn

    uvicorn.run(
        create_app(token=token),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "server",
        "host": args.host,
        "port": args.port,
    }, ""
