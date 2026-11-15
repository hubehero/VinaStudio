"""Thin validation API shared by the CLI; no Qt or HTTP imports."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vinastudio.core.stdio import engine_output_to_stderr
from vinastudio.core.validation import (
    ValidationReport,
    load_manifest_document,
    run_manifest,
)


def validate_manifest(
    manifest: str | Path,
    out_dir: str | Path,
    *,
    case_ids: set[str] | None = None,
    seeds: list[int] | None = None,
    exhaustiveness: int | None = None,
    posebusters: bool = False,
    root: str | Path | None = None,
) -> ValidationReport:
    document = (
        load_manifest_document(manifest, root=root)
        if root is not None
        else load_manifest_document(manifest)
    )
    cases = document.cases
    if posebusters:
        cases = [replace(case, official_posebusters=True) for case in cases]
    with engine_output_to_stderr():
        return run_manifest(
            cases,
            out_dir,
            case_ids=case_ids,
            exhaustiveness=exhaustiveness,
            seeds=seeds,
            dataset=document.dataset,
        )
