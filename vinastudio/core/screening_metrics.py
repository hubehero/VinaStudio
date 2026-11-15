"""Enrichment metrics for virtual-screening rankings.

Labels are supplied by the caller (a sidecar CSV/JSON or an explicit list);
the ranking itself comes from ``screening.jsonl``. Failed runs and unlabeled
ligands are excluded from the metric and counted separately, so an incomplete
screen cannot look like a working enrichment result.

EF, ROC-AUC and BEDROC are descriptive statistics for the labelled set the
caller supplied. They are not evidence that the same ranking generalises to
another library, target or decoy construction.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from vinastudio.core.errors import InvalidInputError
from vinastudio.core.stats import bootstrap_metric_ci

Label = Literal["active", "decoy", "inactive", "unknown"]
_KNOWN_LABELS = {"active", "decoy", "inactive", "unknown"}
_NEGATIVE_LABELS = {"decoy", "inactive"}


@dataclass(frozen=True, slots=True)
class EnrichmentRow:
    ligand_index: int
    name: str
    affinity: float
    label: Label


@dataclass(frozen=True, slots=True)
class EnrichmentMetrics:
    n_total: int
    n_scored: int
    n_failed: int
    n_labeled: int
    n_actives: int
    n_decoys: int
    n_unlabeled: int
    ef1: float | None
    ef5: float | None
    roc_auc: float | None
    bedroc: float | None
    alpha: float
    bootstrap: dict[str, tuple[float, float] | None]
    roc: list[tuple[float, float]]
    enrichment: list[tuple[float, float]]


def _normalise_label(value: Any) -> Label:
    label = str(value or "").strip().lower()
    if label not in _KNOWN_LABELS:
        raise InvalidInputError(
            f"unknown label {value!r}; expected one of {sorted(_KNOWN_LABELS)}"
        )
    return label  # type: ignore[return-value]


def _put_label(
    labels: dict[int | str, Label], key: int | str, label: Label
) -> None:
    previous = labels.get(key)
    if previous is not None and previous != label:
        raise InvalidInputError(
            f"conflicting labels for {key!r}: {previous!r} vs {label!r}"
        )
    labels[key] = label


def labels_from_items(items: list[dict[str, Any]]) -> dict[int | str, Label]:
    """Convert wire-shaped label items to the lookup used by the metric."""
    labels: dict[int | str, Label] = {}
    for item in items:
        if not isinstance(item, dict):
            raise InvalidInputError("each label item must be an object")
        index = item.get("ligandIndex", item.get("ligand_index", item.get("index")))
        name = item.get("name")
        label = _normalise_label(item.get("label"))
        if index is not None and name is not None:
            raise InvalidInputError("a label item has either ligandIndex or name, not both")
        if index is not None:
            try:
                _put_label(labels, int(index), label)
            except (TypeError, ValueError) as exc:
                raise InvalidInputError(f"invalid ligandIndex {index!r}") from exc
        elif isinstance(name, str) and name.strip():
            _put_label(labels, name.strip(), label)
        else:
            raise InvalidInputError("a label item needs ligandIndex or name")
    return labels


def parse_labels_text(text: str) -> dict[int | str, Label]:
    """Parse a CSV or JSON label file.

    CSV needs a header with ``label`` and one of ``name``/``ligand_index``/
    ``index``. JSON is either a list of those objects or a ``{"labels": [...]}``
    object.
    """
    stripped = text.strip()
    if not stripped:
        raise InvalidInputError("label file is empty")
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"label JSON is invalid: {exc}") from exc
        if isinstance(payload, dict):
            payload = payload.get("labels", payload)
        if not isinstance(payload, list):
            raise InvalidInputError("label JSON must be a list or {'labels': [...]}")
        return labels_from_items(payload)

    reader = csv.DictReader(io.StringIO(stripped))
    if reader.fieldnames is None:
        raise InvalidInputError("label CSV needs a header row")
    fieldnames = {name.strip().lower(): name for name in reader.fieldnames}
    if "label" not in fieldnames:
        raise InvalidInputError("label CSV needs a 'label' column")
    index_column = fieldnames.get("ligand_index") or fieldnames.get("index")
    name_column = fieldnames.get("name")
    if index_column is None and name_column is None:
        raise InvalidInputError("label CSV needs a 'name' or 'ligand_index' column")

    labels: dict[int | str, Label] = {}
    for line_number, raw in enumerate(reader, start=2):
        label = _normalise_label(raw.get(fieldnames["label"]))
        if index_column is not None and str(raw.get(index_column) or "").strip():
            try:
                _put_label(labels, int(str(raw[index_column]).strip()), label)
            except ValueError as exc:
                raise InvalidInputError(
                    f"label CSV line {line_number}: ligand_index is not an integer"
                ) from exc
        elif name_column is not None and str(raw.get(name_column) or "").strip():
            _put_label(labels, str(raw[name_column]).strip(), label)
        else:
            raise InvalidInputError(
                f"label CSV line {line_number} has neither name nor ligand_index"
            )
    return labels


def load_labels_path(path: str | Path) -> dict[int | str, Label]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidInputError(f"could not read label file: {exc}") from exc
    return parse_labels_text(text)


def _lookup_label(
    labels: dict[int | str, Label], ligand_index: int, name: str
) -> Label:
    if ligand_index in labels:
        return labels[ligand_index]
    if name in labels:
        return labels[name]
    return "unknown"


def _sorted_rows(rows: list[EnrichmentRow]) -> list[EnrichmentRow]:
    # More negative affinity is better; index makes ties deterministic.
    return sorted(rows, key=lambda row: (row.affinity, row.ligand_index))


def _rank_auc(rows: list[EnrichmentRow]) -> float:
    """Mann-Whitney AUC with average ranks for tied affinities."""
    # Ranks run worst-to-best, which is the convention for the rank-sum AUC.
    ordered = sorted(rows, key=lambda row: (-row.affinity, row.ligand_index))
    ranks: dict[int, float] = {}
    index = 0
    while index < len(ordered):
        end = index
        while (
            end + 1 < len(ordered)
            and ordered[end + 1].affinity == ordered[index].affinity
        ):
            end += 1
        rank = (index + 1 + end + 1) / 2.0
        for position in range(index, end + 1):
            ranks[id(ordered[position])] = rank
        index = end + 1
    actives = [row for row in ordered if row.label == "active"]
    negatives = len(ordered) - len(actives)
    if not actives or negatives <= 0:
        raise InvalidInputError(
            "enrichment needs at least one active and one decoy/inactive label"
        )
    sum_ranks = sum(ranks[id(row)] for row in actives)
    return (sum_ranks - len(actives) * (len(actives) + 1) / 2.0) / (
        len(actives) * negatives
    )


def _ef_value(ordered: list[EnrichmentRow], actives: int, fraction: float) -> float:
    n_top = max(1, math.ceil(len(ordered) * fraction))
    hits = sum(1 for row in ordered[:n_top] if row.label == "active")
    expected = n_top * actives / len(ordered)
    return hits / expected if expected else 0.0


def _metric_values(
    rows: list[EnrichmentRow],
    top_fractions: tuple[float, ...],
    alpha: float,
) -> tuple[dict[str, float], list[float]]:
    from rdkit.ML.Scoring import Scoring

    ordered = _sorted_rows(rows)
    actives = sum(1 for row in ordered if row.label == "active")
    negatives = len(ordered) - actives
    if actives == 0 or negatives == 0:
        raise InvalidInputError(
            "enrichment needs at least one active and one decoy/inactive label"
        )

    scores = [[-row.affinity, row.label == "active"] for row in ordered]
    ef_values = [_ef_value(ordered, actives, fraction) for fraction in top_fractions]

    values = {
        # RDKit's BEDROC can overshoot by one float ulp; the metric is in [0, 1].
        "roc_auc": min(1.0, max(0.0, _rank_auc(ordered))),
        "bedroc": min(1.0, max(0.0, float(Scoring.CalcBEDROC(scores, 1, alpha)))),
    }
    return values, ef_values


def _curves(rows: list[EnrichmentRow]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    ordered = _sorted_rows(rows)
    n = len(ordered)
    actives = sum(1 for row in ordered if row.label == "active")
    if n == 0 or actives == 0:
        return [], []
    step = max(1, n // 200)
    roc: list[tuple[float, float]] = [(0.0, 0.0)]
    enrichment: list[tuple[float, float]] = [(0.0, 1.0)]
    hits = 0
    for index, row in enumerate(ordered, start=1):
        if row.label == "active":
            hits += 1
        if index % step and index != n:
            continue
        fraction = index / n
        roc.append(((index - hits) / (n - actives), hits / actives))
        enrichment.append((fraction, hits / (index * actives / n)))
    return roc, enrichment


def _bootstrap(
    rows: list[EnrichmentRow],
    metric,
    *,
    n: int,
    seed: int,
) -> tuple[float, float] | None:
    return bootstrap_metric_ci(rows, metric, n=n, seed=seed)


def compute_metrics(
    rows: list[dict[str, Any]],
    labels: dict[int | str, Label],
    *,
    top_fractions: tuple[float, ...] = (0.01, 0.05),
    alpha: float = 20.0,
    bootstrap_n: int = 1000,
    seed: int = 42,
) -> EnrichmentMetrics:
    """Compute EF/AUC/BEDROC over a screening run and a label mapping."""
    if not top_fractions or any(f <= 0 or f > 1 for f in top_fractions):
        raise InvalidInputError("top fractions must be in (0, 1]")
    if alpha <= 0:
        raise InvalidInputError("BEDROC alpha must be positive")

    # The jsonl is append-only; if a retry wrote a second row for the same
    # ligand, the latest row is the result the ranking should use.
    deduped: dict[Any, dict[str, Any]] = {}
    for position, row in enumerate(rows):
        key = row.get("i") if isinstance(row.get("i"), int) else f"row-{position}"
        deduped[key] = row
    rows = list(deduped.values())

    completed: list[tuple[int, str, float]] = []
    failed = 0
    for row in rows:
        status = row.get("status")
        if status == "failed":
            failed += 1
            continue
        if status != "completed":
            continue
        affinity = row.get("affinity")
        if not isinstance(affinity, (int, float)) or not math.isfinite(float(affinity)):
            continue
        index = row.get("i")
        try:
            ligand_index = int(index) if index is not None else 0
        except (TypeError, ValueError):
            ligand_index = 0
        completed.append((ligand_index, str(row.get("name") or ""), float(affinity)))

    scored: list[EnrichmentRow] = []
    for ligand_index, name, affinity in completed:
        label = _lookup_label(labels, ligand_index, name)
        if label in {"active", *_NEGATIVE_LABELS}:
            scored.append(
                EnrichmentRow(
                    ligand_index=ligand_index,
                    name=name,
                    affinity=affinity,
                    label=label,
                )
            )

    actives = sum(1 for row in scored if row.label == "active")
    negatives = sum(1 for row in scored if row.label in _NEGATIVE_LABELS)
    if actives == 0 or negatives == 0:
        raise InvalidInputError(
            "enrichment needs at least one active and one decoy/inactive label"
        )

    values, ef_values = _metric_values(scored, top_fractions, alpha)
    top = tuple(top_fractions) + (0.0,) * (2 - len(top_fractions))
    roc, enrichment = _curves(scored)

    def ef_metric(fraction: float):
        def metric(sample: list[EnrichmentRow]) -> float | None:
            ordered = _sorted_rows(sample)
            actives = sum(1 for row in ordered if row.label == "active")
            if actives == 0 or len(ordered) - actives == 0:
                return None
            return _ef_value(ordered, actives, fraction)

        return metric

    def auc_metric(sample: list[EnrichmentRow]) -> float | None:
        try:
            return _rank_auc(sample)
        except InvalidInputError:
            return None

    def bedroc_metric(sample: list[EnrichmentRow]) -> float | None:
        from rdkit.ML.Scoring import Scoring

        ordered = _sorted_rows(sample)
        actives = sum(1 for row in ordered if row.label == "active")
        if actives == 0 or len(ordered) - actives == 0:
            return None
        scores = [[-row.affinity, row.label == "active"] for row in ordered]
        return float(Scoring.CalcBEDROC(scores, 1, alpha))

    bootstrap = {
        "ef1": _bootstrap(scored, ef_metric(top[0]), n=bootstrap_n, seed=seed),
        "ef5": (
            _bootstrap(scored, ef_metric(top[1]), n=bootstrap_n, seed=seed)
            if len(top_fractions) > 1
            else None
        ),
        "roc_auc": _bootstrap(scored, auc_metric, n=bootstrap_n, seed=seed),
        "bedroc": _bootstrap(scored, bedroc_metric, n=bootstrap_n, seed=seed),
    }

    return EnrichmentMetrics(
        n_total=len(rows),
        n_scored=len(completed),
        n_failed=failed,
        n_labeled=len(scored),
        n_actives=actives,
        n_decoys=negatives,
        n_unlabeled=len(completed) - len(scored),
        ef1=ef_values[0] if ef_values else None,
        ef5=ef_values[1] if len(ef_values) > 1 else None,
        roc_auc=values["roc_auc"],
        bedroc=values["bedroc"],
        alpha=alpha,
        bootstrap=bootstrap,
        roc=roc,
        enrichment=enrichment,
    )
