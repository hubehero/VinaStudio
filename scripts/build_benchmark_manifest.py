#!/usr/bin/env python3
"""Build the frozen confirmatory manifest from the audited 12 targets.

All preparation metadata comes from the audit JSON: ligand residue, cofactor
keys, source hashes. The only per-target geometry derived here is the native
ligand centroid and the fixed 22 Å box. No docking result is read.

The generated PDB/SDF/reference files live under ``.benchmark-data/`` and are
never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from rdkit import Chem

REPO_ROOT = Path(__file__).resolve().parent.parent
CCD_URL = "https://files.rcsb.org/ligands/download/{code}_ideal.sdf"
TIMEOUT = 30


def _load_reference_builder():
    path = REPO_ROOT / "scripts" / "build_benchmark_reference.py"
    spec = importlib.util.spec_from_file_location("build_benchmark_reference", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size > 100:
        return
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SystemExit(f"cannot fetch {url}: {exc}") from exc
    if len(payload) < 100 or payload.lstrip().startswith(b"<"):
        raise SystemExit(f"unexpected ligand payload for {url}")
    target.write_bytes(payload)


def _center(reference: Path) -> list[float]:
    mol = Chem.MolFromMolFile(str(reference), removeHs=False)
    if mol is None:
        raise SystemExit(f"cannot read reference {reference}")
    conf = mol.GetConformer()
    points = [
        conf.GetAtomPosition(index)
        for index in range(mol.GetNumAtoms())
        if mol.GetAtomWithIdx(index).GetAtomicNum() > 1
    ]
    if not points:
        raise SystemExit(f"reference has no heavy atoms: {reference}")
    return [
        round(sum(point.x for point in points) / len(points), 3),
        round(sum(point.y for point in points) / len(points), 3),
        round(sum(point.z for point in points) / len(points), 3),
    ]


def build(audit_path: Path, data_root: Path, out_path: Path) -> None:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    selected = audit.get("selected")
    if not isinstance(selected, list) or len(selected) != 12:
        raise SystemExit("audit must contain exactly 12 selected targets")
    try:
        data_root.resolve().relative_to(REPO_ROOT)
    except ValueError as exc:
        raise SystemExit("data root must be inside the repository") from exc

    builder = _load_reference_builder()
    resources: list[dict] = []
    cases: list[dict] = []
    for item in selected:
        pdb_id = item["pdbId"]
        code = item["ligandCode"]
        folder = data_root / "open" / pdb_id.lower()
        folder.mkdir(parents=True, exist_ok=True)
        cached_pdb = REPO_ROOT / ".benchmark-data" / "audit" / f"{pdb_id}.pdb"
        if not cached_pdb.is_file():
            raise SystemExit(f"audited PDB missing: {cached_pdb}")
        pdb_path = folder / f"{pdb_id}.pdb"
        shutil.copy2(cached_pdb, pdb_path)
        ligand_path = folder / f"{code}.sdf"
        _download(CCD_URL.format(code=code), ligand_path)
        builder.build(
            pdb_path,
            ligand_path,
            folder,
            residue=code,
            chain=item.get("ligandChain", ""),
            seq=item.get("ligandSeq", ""),
            name=f"{pdb_id} {code} native ligand",
        )
        reference_path = folder / f"{pdb_id}_reference.sdf"
        center = _center(reference_path)
        relative = (folder.relative_to(REPO_ROOT)).as_posix()
        resource_prefix = f"open/{pdb_id.lower()}"
        resources.extend(
            [
                {
                    "path": f"{resource_prefix}/{pdb_id}.pdb",
                    "url": item["sourceUrl"],
                    "sha256": _sha256(pdb_path),
                },
                {
                    "path": f"{resource_prefix}/{code}.sdf",
                    "url": CCD_URL.format(code=code),
                    "sha256": _sha256(ligand_path),
                },
            ]
        )
        source_sha = _sha256(pdb_path)
        if source_sha != item["sourceSha256"]:
            raise SystemExit(f"PDB hash changed during audit: {pdb_id}")
        cases.append(
            {
                "id": pdb_id.lower(),
                "name": f"{pdb_id} {code} confirmatory redocking",
                "receptor": f"{relative}/{pdb_id}.pdb",
                "ligand": f"{relative}/{code}.sdf",
                "reference": f"{relative}/{pdb_id}_reference.sdf",
                "referenceSource": (
                    f"RCSB PDB {pdb_id} HETATM {code} "
                    f"chain {item.get('ligandChain', '')} {item.get('ligandSeq', '')}; "
                    f"coordinates over CCD {code} graph"
                ),
                "center": center,
                "size": [22.0, 22.0, 22.0],
                "exhaustiveness": 8,
                "nPoses": 9,
                "seed": 42,
                "rmsdThreshold": 2.0,
                "defaultAltloc": "A",
                "allowBadResidues": True,
                "keepHetero": item.get("keepHetero", []),
                "ligandChain": item.get("ligandChain", ""),
                "ligandResidue": code,
                "targetFamily": item.get("family", ""),
                "source": "PDB",
                "license": "CC0-1.0",
                "redistributable": True,
                "sourceUrl": item["sourceUrl"],
                "accessedAt": "2026-11-02",
                "sourceSha256": source_sha,
            }
        )

    payload = {
        "formatVersion": "1.1",
        "dataset": {
            "id": "open-posebusters-v1",
            "name": "Open PoseBusters confirmatory 12",
            "licenseSummary": ["CC0-1.0", "MIT"],
            "redistributable": True,
        },
        "resources": resources,
        "cases": cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path} with {len(cases)} cases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / ".benchmark-data")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    build(args.audit, args.data_root, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
