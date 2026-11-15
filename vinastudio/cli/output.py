"""JSON envelopes and terminal output; stdout never mixes in log text."""

from __future__ import annotations

import json
import sys
from typing import Any

SCHEMA_VERSION = "1.0"


def envelope(ok: bool, command: str, **fields: Any) -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "ok": ok, "command": command, **fields}


def emit_result(
    payload: dict[str, Any], human: str, *, json_mode: bool
) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    elif human:
        print(human)


def emit_error(error: Exception, command: str, *, json_mode: bool) -> None:
    from vinastudio.cli.errors import CliError

    code = error.code if isinstance(error, CliError) else "failure"
    payload = envelope(
        False,
        command,
        error={"code": code, "message": str(error) or type(error).__name__},
    )
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"{command}: {error}", file=sys.stderr)
