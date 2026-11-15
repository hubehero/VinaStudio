"""Read a headless job file and turn Pydantic errors into CLI input errors."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from vinastudio.cli.errors import InputError
from vinastudio.schemas.job import JobConfig
from vinastudio.schemas.screen import ScreenConfig


def load_job(path: str | Path) -> tuple[JobConfig, Path]:
    source = Path(path).expanduser()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"could not read job config: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"job config is not valid JSON: {exc}") from exc
    try:
        config = JobConfig.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "job"
        raise InputError(f"invalid job config at {location}: {first['msg']}") from exc
    return config, source.resolve()


def load_screen(path: str | Path) -> tuple[ScreenConfig, Path]:
    source = Path(path).expanduser()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"could not read screen config: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"screen config is not valid JSON: {exc}") from exc
    try:
        config = ScreenConfig.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "screen"
        raise InputError(f"invalid screen config at {location}: {first['msg']}") from exc
    return config, source.resolve()
