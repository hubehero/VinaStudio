#!/usr/bin/env python3
"""Build the independent 1IEP crystal-ligand reference from the PDB HETATM block.

The upstream tutorial SDF and the PDB crystal ligand happen to have identical
coordinates for 1IEP, so using the SDF for both input and reference is still
circular evidence.  This script records the crystal provenance separately:
extract ``STI A 201`` and its CONECT records, then copy those coordinates onto
the public ligand graph/bond orders.

Usage:
    .venv/bin/python scripts/build_1iep_reference.py \
        --pdb vinastudio/resources/sample/1iep/1iep.pdb \
        --ligand vinastudio/resources/sample/1iep/1iep_ligand.sdf

The command is intentionally strict: an atom-count or element mismatch is a
failure, never a silently guessed mapping.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from rdkit import Chem

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDB = REPO_ROOT / "vinastudio" / "resources" / "sample" / "1iep" / "1iep.pdb"
DEFAULT_LIGAND = REPO_ROOT / "vinastudio" / "resources" / "sample" / "1iep" / "1iep_ligand.sdf"
DEFAULT_OUT = REPO_ROOT / "vinastudio" / "resources" / "sample" / "1iep"
STI_RESIDUE = "STI"
STI_CHAIN = "A"
STI_SEQ = "201"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _crystal_lines(pdb: Path) -> tuple[list[str], list[str]]:
    text = pdb.read_text(encoding="utf-8", errors="replace").splitlines()
    atoms = [
        line
        for line in text
        if line.startswith("HETATM")
        and line[17:20].strip() == STI_RESIDUE
        and line[21:22].strip() == STI_CHAIN
        and line[22:26].strip() == STI_SEQ
    ]
    if not atoms:
        raise SystemExit(f"no {STI_RESIDUE} {STI_CHAIN} {STI_SEQ} HETATM records in {pdb}")
    serials = {int(line[6:11]) for line in atoms}
    conect = [
        line
        for line in text
        if line.startswith("CONECT") and int(line[6:11]) in serials
    ]
    return atoms, conect


def build(pdb: Path, ligand_path: Path, out_dir: Path) -> tuple[Path, Path]:
    atoms, conect = _crystal_lines(pdb)
    ligand = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
    if ligand is None:
        raise SystemExit(f"cannot parse ligand SDF: {ligand_path}")
    heavy = [atom for atom in ligand.GetAtoms() if atom.GetAtomicNum() > 1]
    if len(heavy) != len(atoms):
        raise SystemExit(
            f"atom-count mismatch: SDF heavy atoms={len(heavy)}, PDB STI atoms={len(atoms)}"
        )

    conf = ligand.GetConformer()
    for index, (atom, line) in enumerate(zip(heavy, atoms, strict=True)):
        element = line[76:78].strip().upper()
        if atom.GetSymbol().upper() != element:
            raise SystemExit(
                f"element mismatch at heavy atom {index}: SDF {atom.GetSymbol()} PDB {element}"
            )
        x, y, z = (float(line[start:start + 8]) for start in (30, 38, 46))
        old = conf.GetAtomPosition(atom.GetIdx())
        # The upstream tutorial SDF and this PDB block are expected to be the
        # same deposition; record a warning-worthy drift rather than hiding it.
        drift = ((old.x - x) ** 2 + (old.y - y) ** 2 + (old.z - z) ** 2) ** 0.5
        if drift > 0.01:
            print(f"note: heavy atom {index} differs from PDB by {drift:.4f} A")
        conf.SetAtomPosition(atom.GetIdx(), (x, y, z))

    reference = Chem.RemoveHs(ligand)
    reference.SetProp("_Name", "1IEP crystal ligand STI A 201")
    out_dir.mkdir(parents=True, exist_ok=True)
    crystal_path = out_dir / "1iep_crystal_ligand.pdb"
    reference_path = out_dir / "1iep_reference.sdf"
    crystal_path.write_text("\n".join(atoms + conect + ["END"]) + "\n", encoding="utf-8")
    Chem.MolToMolFile(reference, str(reference_path))
    print(f"crystal PDB: {crystal_path} ({len(atoms)} atoms, {len(conect)} CONECT)")
    print(f"reference SDF: {reference_path}")
    print(f"crystal SHA-256: {_sha256(crystal_path)}")
    print(f"reference SHA-256: {_sha256(reference_path)}")
    return crystal_path, reference_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdb", type=Path, default=DEFAULT_PDB)
    parser.add_argument("--ligand", type=Path, default=DEFAULT_LIGAND)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build(args.pdb, args.ligand, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
