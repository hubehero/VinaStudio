#!/usr/bin/env python3
"""Write the committed JSON Schema files from the Pydantic contract models."""

from __future__ import annotations

import json
from pathlib import Path

from vinastudio.schemas.job import JOB_SCHEMA_VERSION, JobConfig
from vinastudio.schemas.result import RESULT_SCHEMA_VERSION, DockResult
from vinastudio.schemas.screen import SCREEN_SCHEMA_VERSION, ScreenConfig

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def _schema(model, schema_id: str) -> dict:
    payload = model.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        **payload,
    }


def main() -> int:
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    files = {
        f"job-{JOB_SCHEMA_VERSION}.schema.json": _schema(
            JobConfig, f"urn:vinastudio:job:{JOB_SCHEMA_VERSION}"
        ),
        f"result-{RESULT_SCHEMA_VERSION}.schema.json": _schema(
            DockResult, f"urn:vinastudio:result:{RESULT_SCHEMA_VERSION}"
        ),
        f"screen-{SCREEN_SCHEMA_VERSION}.schema.json": _schema(
            ScreenConfig, f"urn:vinastudio:screen:{SCREEN_SCHEMA_VERSION}"
        ),
    }
    for name, payload in files.items():
        (SCHEMAS / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(SCHEMAS / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
