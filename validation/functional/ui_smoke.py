#!/usr/bin/env python3
"""Reproducible UI route smoke for VinaStudio's production SPA.

This is a *route/landmark* check, not a substitute for the interaction
walkthrough in ``README.md``. It drives the locally installed ``agent-browser``
CLI (Chrome/CDP) against a running VinaStudio server, records the visible
landmark for each route, and saves a screenshot per route.

Prerequisite:
    npm i -g agent-browser && agent-browser install

Example:
    uv run python validation/functional/ui_smoke.py \
        --base-url http://127.0.0.1:8760 \
        --out validation/functional/records/2026-10-30

The server must serve the built SPA (``scripts/build_web.py``), not the Vite
dev server, so the recorded hashes refer to the shipped interface.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROUTES: list[tuple[str, str, str]] = [
    ("workbench", "对接流程", "工作台 / 5-step pipeline"),
    ("molecules", "分子目录", "Catalog"),
    ("box", "结合位点盒子", "Box / search space"),
    ("docking", "参数", "Docking inspector (tabs: Parameters / Analysis / Results)"),
    ("report", "结果汇报", "Report"),
    ("batch", "批量筛选", "Batch docking"),
    ("screening", "虚拟筛选工作台", "Screening"),
    ("results", "历史检索", "Results search"),
    ("environment", "环境自检", "Environment"),
    ("help", "使用帮助", "Help"),
    ("about", "关于", "About"),
]

# A page that renders its shell but shows one of these strings has failed to
# load its data or its route component; surface it as a failure, not a pass.
ERROR_MARKERS = (
    "Failed to fetch",
    "Cannot read propert",
    "Internal Server Error",
    "TypeError:",
)


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["agent-browser", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def _eval_json(script: str) -> object:
    result = _run("eval", script)
    # The CLI may print a status line before the value; the value is the last
    # complete JSON line. Keep parsing bounded to the final line.
    line = result.stdout.strip().splitlines()[-1]
    value = json.loads(line)
    # ``agent-browser eval`` JSON-encodes the returned string, so an object
    # arrives as a quoted JSON string and needs a second decode.
    if isinstance(value, str):
        value = json.loads(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8760")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args(argv)

    if subprocess.run(
        ["agent-browser", "--version"], capture_output=True, text=True
    ).returncode != 0:
        print("agent-browser is not installed; see the docstring", file=sys.stderr)
        return 2

    out = args.out
    ui_dir = out / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    _run("set", "viewport", str(args.width), str(args.height))

    records: list[dict[str, object]] = []
    for route, landmark, title in ROUTES:
        url = f"{args.base_url}/#/{route}"
        _run("open", url)
        _run("wait", "700")
        state = _eval_json(
            "JSON.stringify({"
            "hash: location.hash, "
            f"landmark: document.body.innerText.includes({json.dumps(landmark)}), "
            "body: document.body.innerText.slice(0, 1200)"
            "})"
        )
        assert isinstance(state, dict)
        body = str(state.get("body", ""))
        screenshot = ui_dir / f"{route}.png"
        _run("screenshot", str(screenshot))
        records.append(
            {
                "route": route,
                "title": title,
                "url": url,
                "expectedLandmark": landmark,
                "landmarkFound": bool(state.get("landmark")),
                "hash": state.get("hash"),
                "errorMarkers": [marker for marker in ERROR_MARKERS if marker in body],
                "screenshot": str(screenshot.relative_to(out)),
            }
        )

    payload = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "baseUrl": args.base_url,
        "tool": _run("--version").stdout.strip(),
        "routes": records,
        "summary": {
            "total": len(records),
            "passed": sum(
                1
                for record in records
                if record["landmarkFound"] and not record["errorMarkers"]
            ),
            "failed": sum(
                1
                for record in records
                if not record["landmarkFound"] or record["errorMarkers"]
            ),
        },
    }
    destination = out / "ui-smoke.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"UI smoke: {destination}")
    print(payload["summary"])
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
