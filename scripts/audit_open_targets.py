#!/usr/bin/env python3
"""Audit PoseBusters targets and freeze a confirmatory 12-target selection.

The audit deliberately uses only deposited PDB metadata and geometry. It never
runs docking and never looks at a Vina score. PDB files are cached outside the
repository (``.benchmark-data/audit``); the JSON output contains ids, metadata,
licence and hashes, not structures.

Protocol rules implemented here:
  * exclude the four pilot IDs;
  * resolution <= 2.5 A;
  * ligand heavy atoms 8-40;
  * no LINK record connecting the ligand to the polymer;
  * keep non-water HETATM groups within 6.0 A of a ligand heavy atom;
  * max two targets per PDB COMPND molecule family;
  * deterministic SHA-256 ranking with a fixed selection seed.

This is a pre-registration helper, not a docking result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_IDS = {"5SB2", "5SD5", "5SIS", "6M2B"}
BUFFER_CODES = {
    "HOH", "EDO", "GOL", "DMS", "IMD", "SO4", "PO4", "ACT", "FMT", "PEG",
    "MOH", "MPD", "TRS", "EPE", "CIT", "TAR", "ACE", "NH4", "NO3", "MES",
}
DISTANCE_CUTOFF = 6.0
RESOLUTION_LIMIT = 2.5
MIN_HEAVY = 8
MAX_HEAVY = 40
PDB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
TIMEOUT = 30


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pool(path: Path) -> list[tuple[str, str]]:
    tokens = path.read_text(encoding="utf-8").replace(",", " ").split()
    if len(tokens) % 2:
        raise SystemExit("pool must contain PDB/ligand pairs")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index in range(0, len(tokens), 2):
        pdb_id, ligand = tokens[index].upper(), tokens[index + 1].upper()
        if len(pdb_id) != 4 or not pdb_id[0].isdigit():
            raise SystemExit(f"invalid PDB ID: {pdb_id!r}")
        if pdb_id not in seen:
            entries.append((pdb_id, ligand))
            seen.add(pdb_id)
    return entries


def _download(pdb_id: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{pdb_id}.pdb"
    if target.is_file() and target.stat().st_size > 1000:
        return target
    url = PDB_URL.format(pdb_id=pdb_id)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SystemExit(f"cannot fetch {pdb_id}: {exc}") from exc
    if not payload.startswith((b"HEADER", b"TITLE", b"ATOM", b"HETATM")):
        raise SystemExit(f"unexpected PDB payload for {pdb_id}")
    target.write_bytes(payload)
    return target


def _resolution(lines: list[str]) -> float | None:
    for line in lines:
        if line.startswith("REMARK   2 RESOLUTION."):
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", line)
            if match:
                return float(match.group(1))
    return None


def _family(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("COMPND") and "MOLECULE:" in line:
            value = line.split("MOLECULE:", 1)[1].strip().rstrip(";")
            if value:
                return value
    return "unknown"


def _residue(line: str) -> tuple[str, str, str]:
    return (line[17:20].strip(), line[21:22].strip(), line[22:26].strip())


def _has_altloc_a(lines: list[str]) -> bool:
    return any(line[16:17] in {"A", "B", "C", "D"} for line in lines if line.startswith(("ATOM", "HETATM")))


def inspect_pdb(pdb_id: str, ligand: str, pdb_path: Path) -> dict:
    lines = pdb_path.read_text(encoding="utf-8", errors="replace").splitlines()
    ligand_atoms: list[tuple[float, float, float]] = []
    ligand_residues: set[tuple[str, str, str]] = set()
    all_atoms: list[tuple[str, str, str, str, float, float, float, bool]] = []
    for line in lines:
        if not line.startswith(("ATOM", "HETATM")):
            continue
        residue, chain, seq = _residue(line)
        element = line[76:78].strip().upper()
        try:
            x, y, z = (float(line[start:start + 8]) for start in (30, 38, 46))
        except ValueError:
            continue
        all_atoms.append(
            (residue, chain, seq, element, x, y, z, line.startswith("HETATM"))
        )
        if residue == ligand and line[16:17] in {" ", "A"}:
            ligand_residues.add((residue, chain, seq))
            if element != "H":
                ligand_atoms.append((x, y, z))

    heavy = len(ligand_atoms)
    if not heavy and ligand_residues:
        # If the ligand has only B/C altlocs, use all non-hydrogen ligand atoms.
        ligand_atoms = [
            (x, y, z)
            for residue, _chain, _seq, element, x, y, z, _hetero in all_atoms
            if residue == ligand and element != "H"
        ]
        heavy = len(ligand_atoms)

    ligand_chain = ""
    ligand_seq = ""
    if ligand_residues:
        _res, ligand_chain, ligand_seq = sorted(ligand_residues)[0]
    elif any(item[0] == ligand for item in all_atoms):
        _res, ligand_chain, ligand_seq, _el, _x, _y, _z, _h = next(
            item for item in all_atoms if item[0] == ligand
        )

    covalent = any(
        line.startswith("LINK")
        and (line[17:20].strip() == ligand or line[47:50].strip() == ligand)
        for line in lines
    )
    keep: list[str] = []
    kept_details: list[dict] = []
    if ligand_atoms:
        seen: set[tuple[str, str, str]] = set()
        for residue, chain, seq, element, x, y, z, hetero in all_atoms:
            key = (residue, chain, seq)
            if not hetero or key in seen or residue == ligand or residue in BUFFER_CODES:
                continue
            if element == "H":
                continue
            minimum = min(math.dist((x, y, z), point) for point in ligand_atoms)
            if minimum <= DISTANCE_CUTOFF:
                seen.add(key)
                keep.append(f"{chain}:{seq}")
                kept_details.append(
                    {
                        "residue": residue,
                        "key": f"{chain}:{seq}",
                        "minDistance": round(minimum, 3),
                    }
                )

    span = 0.0
    if ligand_atoms:
        span = max(
            max(point[i] for point in ligand_atoms) - min(point[i] for point in ligand_atoms)
            for i in range(3)
        )
    resolution = _resolution(lines)
    reasons: list[str] = []
    if resolution is None or resolution > RESOLUTION_LIMIT:
        reasons.append("resolution > 2.5 A or unknown")
    if not (MIN_HEAVY <= heavy <= MAX_HEAVY):
        reasons.append(f"ligand heavy atoms {heavy} outside 8-40")
    if covalent:
        reasons.append("LINK record connects ligand to polymer")
    if not ligand_atoms:
        reasons.append("no unambiguous ligand HETATM")
    return {
        "pdbId": pdb_id,
        "ligandCode": ligand,
        "source": "PDB",
        "license": "CC0-1.0",
        "redistributable": True,
        "sourceUrl": PDB_URL.format(pdb_id=pdb_id),
        "sourceSha256": sha256(pdb_path),
        "resolution": resolution,
        "family": _family(lines),
        "ligandChain": ligand_chain,
        "ligandSeq": ligand_seq,
        "heavyAtoms": heavy,
        "span": round(span, 3),
        "hasAltloc": _has_altloc_a(lines),
        "covalent": covalent,
        "keepHetero": keep,
        "keptHetero": kept_details,
        "eligible": not reasons,
        "reasons": reasons,
    }


def select_audited(audit: list[dict], *, count: int, seed: int) -> list[dict]:
    eligible = [item for item in audit if item["eligible"] and item["pdbId"] not in PILOT_IDS]
    eligible.sort(
        key=lambda item: hashlib.sha256(
            f"{seed}:{item['pdbId']}:{item['ligandCode']}".encode("ascii")
        ).hexdigest()
    )
    selected: list[dict] = []
    family_counts: dict[str, int] = {}
    for item in eligible:
        family = item.get("family", "unknown")
        if family_counts.get(family, 0) >= 2:
            continue
        selected.append(item)
        family_counts[family] = family_counts.get(family, 0) + 1
        if len(selected) == count:
            break
    if len(selected) < count:
        raise SystemExit(
            f"only {len(selected)} eligible targets after family cap; widen the audit limit"
        )
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=REPO_ROOT / ".benchmark-data" / "audit")
    parser.add_argument("--limit", type=int, default=24, help="maximum PDBs to inspect")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    entries = [entry for entry in parse_pool(args.pool) if entry[0] not in PILOT_IDS]
    entries.sort(
        key=lambda entry: hashlib.sha256(
            f"{args.seed}:{entry[0]}:{entry[1]}".encode("ascii")
        ).hexdigest()
    )
    audit: list[dict] = []
    for pdb_id, ligand in entries[: args.limit]:
        try:
            pdb_path = _download(pdb_id, args.cache)
            audit.append(inspect_pdb(pdb_id, ligand, pdb_path))
        except SystemExit as exc:
            audit.append(
                {
                    "pdbId": pdb_id,
                    "ligandCode": ligand,
                    "eligible": False,
                    "reasons": [str(exc)],
                }
            )
    selected = select_audited(audit, count=args.count, seed=args.seed)
    payload = {
        "formatVersion": "1.0",
        "selectionSeed": args.seed,
        "count": args.count,
        "pool": str(args.pool),
        "excludedPilots": sorted(PILOT_IDS),
        "limit": args.limit,
        "selected": [
            {
                key: item[key]
                for key in (
                    "pdbId",
                    "ligandCode",
                    "ligandChain",
                    "ligandSeq",
                    "family",
                    "keepHetero",
                    "sourceUrl",
                    "sourceSha256",
                )
            }
            for item in selected
        ],
        "audit": audit,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in selected:
        print(f"SELECT {item['pdbId']} {item['ligandCode']} family={item['family']}")
    print(f"audited {len(audit)}; selected {len(selected)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
