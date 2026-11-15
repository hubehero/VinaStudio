"""Build a screening label sidecar from local active/inactive molecule files.

The output is the CSV consumed by ``POST /api/screening/runs/{id}/metrics``
(``name,label``). Names are the molecule titles, so they must match the titles
used when the library was imported. This script does not download or
redistribute any dataset; LIT-PCBA users are responsible for its terms.

Usage:
    uv run python scripts/build_screening_labels.py \
        --actives path/to/actives.smi --inactives path/to/inactives.smi \
        --out labels.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _smi_names(path: Path) -> list[str]:
    names: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        name = parts[1] if len(parts) > 1 else f"{path.stem}-{line_number}"
        names.append(name)
    return names


def _sdf_names(path: Path) -> list[str]:
    from rdkit import Chem

    names: list[str] = []
    supplier = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False)
    for index, mol in enumerate(supplier, start=1):
        if mol is None:
            continue
        name = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else ""
        names.append(name or f"{path.stem}-{index}")
    return names


def names_from_file(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".smi", ".txt"}:
        return _smi_names(path)
    if suffix in {".sdf", ".sd", ".mol"}:
        return _sdf_names(path)
    raise ValueError(f"unsupported molecule file: {path}")


def build_labels(actives: Path, inactives: Path) -> list[tuple[str, str]]:
    active_names = names_from_file(actives)
    inactive_names = names_from_file(inactives)
    overlap = set(active_names) & set(inactive_names)
    if overlap:
        raise ValueError(
            "the same name is labelled active and inactive: " + ", ".join(sorted(overlap)[:5])
        )
    return [(name, "active") for name in active_names] + [
        (name, "inactive") for name in inactive_names
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actives", type=Path, required=True)
    parser.add_argument("--inactives", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = build_labels(args.actives, args.inactives)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "label"])
        writer.writerows(rows)
    print(f"wrote {len(rows)} labels to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
