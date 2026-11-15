"""Headless library screening over the existing ``screening_worker``.

One process, one shard: this is the honest A2 scope. The worker is reused
directly (not imported from FastAPI job_manager), so the ranking and per-entry
artifacts follow the same preparation/docking path as the GUI.
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vinastudio.api.prepare import (
    prepare_receptor,
    receptor_options_from_schema,
)
from vinastudio.api.result import write_json_atomic
from vinastudio.core.box import Box
from vinastudio.core.chem.library import load_detail
from vinastudio.core.errors import InvalidInputError
from vinastudio.core.screening_metrics import EnrichmentMetrics, compute_metrics, load_labels_path
from vinastudio.core.stdio import engine_output_to_stderr
from vinastudio.core.worker import screening_worker
from vinastudio.schemas.screen import ScreenConfig

_SCREEN_FIELDS = (
    "rank",
    "ligand_index",
    "name",
    "status",
    "affinity",
    "n_poses",
    "qed",
    "lipinski_violations",
    "out_dir",
    "error",
)


@dataclass(slots=True)
class ScreenRun:
    rows: list[dict[str, Any]]
    ranking_path: Path
    ranking_json_path: Path
    enrichment: EnrichmentMetrics | None
    enrichment_path: Path | None
    output_dir: Path


class _Collector:
    """The worker's pipe contract is ``send(event)``; no process needed."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate)


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise InvalidInputError(f"{label} not found: {path}")
    return path.resolve()


def _prepare_receptor(
    config: ScreenConfig,
    base: Path,
    output: Path,
) -> Path:
    source = _require_file(_resolve(base, config.receptor.path), "receptor")
    if source.suffix.lower() == ".pdbqt":
        target = output / "receptor.pdbqt"
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        return target
    preparation = prepare_receptor(
        source, receptor_options_from_schema(config.receptor.preparation)
    )
    target = output / "receptor.pdbqt"
    target.write_text(preparation.pdbqt, encoding="utf-8")
    return target


def _entries(
    config: ScreenConfig, base: Path, libdir: Path
) -> list[dict[str, Any]]:
    if config.entries is not None:
        entries: list[dict[str, Any]] = []
        for entry in config.entries:
            item: dict[str, Any] = {"index": entry.index, "name": entry.name}
            if entry.sdfPath:
                item["sdfPath"] = str(_resolve(base, entry.sdfPath))
            if entry.pdbqtPath:
                item["pdbqtPath"] = str(_resolve(base, entry.pdbqtPath))
            entries.append(item)
        return entries

    detail = load_detail(libdir.name, root=libdir.parent)
    if detail is None:
        raise InvalidInputError(f"library index not found: {libdir}")
    return [
        {"index": int(row["index"]), "name": str(row["name"])}
        for row in detail["entries"]
    ]


def _row(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "i": int(event.get("ligandIndex") or 0),
        "name": str(event.get("label") or ""),
        "status": str(event.get("status") or "failed"),
        "affinity": event.get("bestAffinity"),
        "nPoses": event.get("nPoses"),
        "qed": event.get("qed"),
        "lipinski": event.get("lipinskiViolations"),
        "smiles": event.get("smiles"),
        "outDir": event.get("outDir"),
        "error": event.get("error"),
    }


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda row: (
            row["status"] != "completed",
            row["affinity"] is None,
            float(row["affinity"]) if row["affinity"] is not None else 0.0,
            row["i"],
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _write_ranking(output: Path, rows: list[dict[str, Any]]) -> tuple[Path, Path]:
    csv_path = output / "ranking.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_SCREEN_FIELDS)
        for row in rows:
            writer.writerow(
                [
                    row["rank"],
                    row["i"],
                    row["name"],
                    row["status"],
                    "" if row["affinity"] is None else row["affinity"],
                    "" if row["nPoses"] is None else row["nPoses"],
                    "" if row["qed"] is None else row["qed"],
                    "" if row["lipinski"] is None else row["lipinski"],
                    row["outDir"] or "",
                    row["error"] or "",
                ]
            )
    json_path = output / "ranking.json"
    write_json_atomic(
        json_path,
        {
            "schemaVersion": "1.0",
            "rows": [
                {
                    "rank": row["rank"],
                    "ligandIndex": row["i"],
                    "name": row["name"],
                    "status": row["status"],
                    "affinity": row["affinity"],
                    "nPoses": row["nPoses"],
                    "qed": row["qed"],
                    "lipinskiViolations": row["lipinski"],
                    "smiles": row["smiles"],
                    "outDir": row["outDir"],
                    "error": row["error"],
                }
                for row in rows
            ],
        },
    )
    return csv_path, json_path


def _enrichment_payload(metrics: EnrichmentMetrics) -> dict[str, Any]:
    return {
        "nTotal": metrics.n_total,
        "nScored": metrics.n_scored,
        "nFailed": metrics.n_failed,
        "nLabeled": metrics.n_labeled,
        "nActives": metrics.n_actives,
        "nDecoys": metrics.n_decoys,
        "nUnlabeled": metrics.n_unlabeled,
        "ef1": metrics.ef1,
        "ef5": metrics.ef5,
        "rocAuc": metrics.roc_auc,
        "bedroc": metrics.bedroc,
        "alpha": metrics.alpha,
        "bootstrap": {
            key: list(value) if value is not None else None
            for key, value in metrics.bootstrap.items()
        },
        "roc": [[x, y] for x, y in metrics.roc],
        "enrichment": [[x, y] for x, y in metrics.enrichment],
    }


def _write_enrichment(
    output: Path, metrics: EnrichmentMetrics
) -> Path:
    json_path = output / "enrichment.json"
    write_json_atomic(json_path, _enrichment_payload(metrics))
    csv_path = output / "enrichment.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value", "ci_low", "ci_high"])
        for name, value, ci in (
            ("ef1", metrics.ef1, metrics.bootstrap.get("ef1")),
            ("ef5", metrics.ef5, metrics.bootstrap.get("ef5")),
            ("roc_auc", metrics.roc_auc, metrics.bootstrap.get("roc_auc")),
            ("bedroc", metrics.bedroc, metrics.bootstrap.get("bedroc")),
        ):
            writer.writerow(
                [
                    name,
                    "" if value is None else f"{value:.6g}",
                    "" if ci is None else f"{ci[0]:.6g}",
                    "" if ci is None else f"{ci[1]:.6g}",
                ]
            )
    return json_path


def screen(
    config: ScreenConfig,
    out_dir: str | Path,
    *,
    base_dir: str | Path | None = None,
    parallelism: int = 1,
) -> ScreenRun:
    if parallelism != 1:
        raise InvalidInputError(
            "headless screen currently supports --parallelism 1 only"
        )
    base = Path(base_dir or Path.cwd()).resolve()
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    libdir = _resolve(base, config.libraryPath).resolve()
    if not libdir.is_dir():
        raise InvalidInputError(f"library not found: {libdir}")

    receptor = _prepare_receptor(config, base, output)
    flex = None
    if config.parameters.flexReceptorPath:
        flex = _require_file(
            _resolve(base, config.parameters.flexReceptorPath), "flexible receptor"
        )
        target = output / "flex.pdbqt"
        if flex.resolve() != target.resolve():
            shutil.copyfile(flex, target)
        flex = target

    box = config.box
    if box.center is None or box.size is None:
        raise InvalidInputError("screening needs a manual box")
    box_value = Box(
        center=box.center,
        size=box.size,
        spacing=box.spacing,
        force_even_voxels=box.forceEvenVoxels,
    )
    parameters = config.parameters
    worker_params: dict[str, Any] = {
        "job_id": "headless-screen",
        "output_dir": str(output / "ligands"),
        "entries": _entries(config, base, libdir),
        "library_dir": str(libdir),
        "shard_index": 0,
        "shard_count": 1,
        "receptor_path": str(receptor),
        "flex_pdbqt_path": str(flex) if flex is not None else None,
        "center": list(box_value.center),
        "size": list(box_value.size),
        "scoring": parameters.scoring,
        "exhaustiveness": parameters.exhaustiveness,
        "n_poses": parameters.nPoses,
        "energy_range": parameters.energyRange,
        "min_rmsd": parameters.minRmsd,
        "spacing": box_value.spacing,
        "force_even_voxels": box_value.force_even_voxels,
        "cpu": parameters.cpu,
        "seed": parameters.seed,
        "no_refine": parameters.noRefine,
        "engine": parameters.engine,
    }
    collector = _Collector()
    with engine_output_to_stderr():
        screening_worker(dict(worker_params), collector)  # type: ignore[arg-type]

    rows = _sort_rows(
        [
            _row(event)
            for event in collector.events
            if event.get("type") == "ligand_completed"
        ]
    )
    ranking_path, ranking_json_path = _write_ranking(output, rows)

    enrichment = None
    enrichment_path = None
    if config.labelsPath:
        labels = load_labels_path(_resolve(base, config.labelsPath))
        enrichment = compute_metrics(
            rows, labels, alpha=config.enrichmentAlpha
        )
        enrichment_path = _write_enrichment(output, enrichment)

    return ScreenRun(
        rows=rows,
        ranking_path=ranking_path,
        ranking_json_path=ranking_json_path,
        enrichment=enrichment,
        enrichment_path=enrichment_path,
        output_dir=output,
    )
