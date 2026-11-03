#!/usr/bin/env python3
"""Select a deterministic, pre-registerable target list from PoseBusters.

The selection is based only on the public ID/ligand list and a fixed seed. It is
recorded before any docking result exists. It does not download structures, and
it does not inspect docking scores.

Input format: the upstream PoseBusters list, e.g.
    ``6M2B EZO, 6M73 FNR, ...``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "validation" / "benchmark" / "manifests" / "open-posebusters-selection.json"
_PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_LIGAND_RE = re.compile(r"^[A-Za-z0-9]{1,4}$")


def parse_pool(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    tokens = text.replace(",", " ").split()
    if len(tokens) % 2:
        raise SystemExit("pool must contain PDB/ligand pairs; found an odd token count")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index in range(0, len(tokens), 2):
        pdb_id, ligand = tokens[index].upper(), tokens[index + 1].upper()
        if not _PDB_RE.fullmatch(pdb_id):
            raise SystemExit(f"invalid PDB ID at token {index}: {pdb_id!r}")
        if not _LIGAND_RE.fullmatch(ligand):
            raise SystemExit(f"invalid ligand code at token {index + 1}: {ligand!r}")
        if pdb_id in seen:
            continue
        seen.add(pdb_id)
        entries.append((pdb_id, ligand))
    return entries


def select(
    entries: list[tuple[str, str]],
    *,
    count: int,
    pilot: int,
    seed: int,
    exclude: set[str],
) -> list[dict]:
    if count <= 0 or pilot <= 0 or pilot > count:
        raise SystemExit("need count > 0 and 0 < pilot <= count")
    candidates = [entry for entry in entries if entry[0] not in exclude]
    if len(candidates) < count:
        raise SystemExit(f"need {count} targets, pool has {len(candidates)} after exclusions")
    ranked = sorted(
        candidates,
        key=lambda entry: hashlib.sha256(
            f"{seed}:{entry[0]}:{entry[1]}".encode("ascii")
        ).hexdigest(),
    )
    chosen = ranked[:count]
    return [
        {
            "id": pdb_id.lower(),
            "pdbId": pdb_id,
            "ligandCode": ligand,
            "pilot": index < pilot,
            "source": "PoseBusters-Benchmark",
            "license": "MIT",
            "redistributable": True,
        }
        for index, (pdb_id, ligand) in enumerate(chosen)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--pilot", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--exclude", action="append", default=[], metavar="PDB_ID")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    entries = parse_pool(args.pool)
    targets = select(
        entries,
        count=args.count,
        pilot=args.pilot,
        seed=args.seed,
        exclude={value.upper() for value in args.exclude},
    )
    payload = {
        "formatVersion": "1.0",
        "datasetId": "open-posebusters-v1",
        "sourcePool": str(args.pool),
        "seed": args.seed,
        "count": args.count,
        "pilot": args.pilot,
        "targets": targets,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for target in targets:
        marker = "PILOT" if target["pilot"] else "     "
        print(f"{marker} {target['pdbId']} {target['ligandCode']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
