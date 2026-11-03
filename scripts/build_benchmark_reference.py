#!/usr/bin/env python3
"""Build a crystal-coordinate reference for a PDB ligand.

The ligand *graph* comes from an SDF (normally the PDB Chemical Component
Dictionary); the *coordinates* come from the deposited PDB HETATM block. This
keeps the input and reference paths distinct and makes the provenance auditable.
Atom/element mismatches are hard failures, never silently reordered.

Example:
    uv run python scripts/build_benchmark_reference.py \
      --pdb .benchmark-data/open/6m2b/6m2b.pdb \
      --ligand .benchmark-data/open/6m2b/EZO.sdf \
      --residue EZO --chain A --seq 201 \
      --out-dir .benchmark-data/open/6m2b
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from rdkit import Chem

REPO_ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crystal_lines(pdb: Path, residue: str, chain: str, seq: str) -> tuple[list[str], list[str]]:
    text = pdb.read_text(encoding="utf-8", errors="replace").splitlines()
    atoms = [
        line
        for line in text
        if line.startswith("HETATM")
        and line[17:20].strip() == residue
        and (not chain or line[21:22].strip() == chain)
        and (not seq or line[22:26].strip() == seq)
        and line[16:17] in {" ", "A"}
        and line[76:78].strip().upper() != "H"
    ]
    if not atoms:
        selector = f"{residue} {chain or '*'} {seq or '*'}"
        raise SystemExit(f"no HETATM records for {selector} in {pdb}")
    serials = {int(line[6:11]) for line in atoms}
    conect = [
        line
        for line in text
        if line.startswith("CONECT") and int(line[6:11]) in serials
    ]
    return atoms, conect


def build(
    pdb: Path,
    ligand_path: Path,
    out_dir: Path,
    *,
    residue: str,
    chain: str,
    seq: str,
    name: str,
) -> tuple[Path, Path]:
    atoms, conect = crystal_lines(pdb, residue, chain, seq)
    ligand = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
    if ligand is None:
        raise SystemExit(f"cannot parse ligand SDF: {ligand_path}")
    heavy = [atom for atom in ligand.GetAtoms() if atom.GetAtomicNum() > 1]
    if len(heavy) != len(atoms):
        raise SystemExit(
            f"atom-count mismatch: SDF heavy atoms={len(heavy)}, PDB HETATM={len(atoms)}"
        )

    conf = ligand.GetConformer()
    for index, (atom, line) in enumerate(zip(heavy, atoms, strict=True)):
        element = line[76:78].strip().upper()
        if atom.GetSymbol().upper() != element:
            raise SystemExit(
                f"element mismatch at heavy atom {index}: "
                f"SDF {atom.GetSymbol()} PDB {element}"
            )
        x, y, z = (float(line[start:start + 8]) for start in (30, 38, 46))
        conf.SetAtomPosition(atom.GetIdx(), (x, y, z))

    reference = Chem.RemoveHs(ligand)
    reference.SetProp("_Name", name)
    out_dir.mkdir(parents=True, exist_ok=True)
    crystal_path = out_dir / f"{pdb.stem}_crystal_ligand.pdb"
    reference_path = out_dir / f"{pdb.stem}_reference.sdf"
    crystal_path.write_text("\n".join(atoms + conect + ["END"]) + "\n", encoding="utf-8")
    Chem.MolToMolFile(reference, str(reference_path))
    print(f"crystal PDB: {crystal_path} ({len(atoms)} atoms, {len(conect)} CONECT)")
    print(f"reference SDF: {reference_path}")
    print(f"crystal SHA-256: {sha256(crystal_path)}")
    print(f"reference SHA-256: {sha256(reference_path)}")
    return crystal_path, reference_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdb", type=Path, required=True)
    parser.add_argument("--ligand", type=Path, required=True)
    parser.add_argument("--residue", required=True)
    parser.add_argument("--chain", default="")
    parser.add_argument("--seq", default="")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)
    build(
        args.pdb,
        args.ligand,
        args.out_dir,
        residue=args.residue,
        chain=args.chain,
        seq=args.seq,
        name=args.name or f"{args.pdb.stem} {args.residue} crystal ligand",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
