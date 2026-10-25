"""Stable molecule identity for catalog deduplication.

A filesystem path is not an identity: the same ligand can arrive as SDF,
PDBQT or a provider download.  Ligands use a full InChIKey when RDKit can
parse them; the parent key is kept separately for "possibly same scaffold/salt"
suggestions.  Receptors use a PDB id when one is visible in the filename,
otherwise a content hash.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

from vinastudio.core.chem.pdbqt import _SMILES_RE
from vinastudio.core.chem.rdkit_io import mol_from_file

_PDB_ID = re.compile(r"(?:^|[_-])([0-9][A-Za-z0-9]{3})(?:[_-]|$)")


@dataclass(frozen=True, slots=True)
class Identity:
    key: str
    kind: str
    canonical_smiles: str | None = None
    inchi_key: str | None = None
    parent_inchi_key: str | None = None
    formula: str | None = None
    molecular_weight: float | None = None


def content_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_inchi(mol: Chem.Mol) -> str | None:
    try:
        value = Chem.MolToInchiKey(mol)
    except (RuntimeError, ValueError):
        return None
    return value or None


def _safe_smiles(mol: Chem.Mol) -> str | None:
    try:
        return Chem.MolToSmiles(mol, isomericSmiles=True)
    except (RuntimeError, ValueError):
        return None


def identity_from_mol(mol: Chem.Mol) -> Identity:
    """Ligand identity from a parsed RDKit molecule."""
    inchi_key = _safe_inchi(mol)
    smiles = _safe_smiles(mol)
    parent_key: str | None = None
    try:
        parent = rdMolStandardize.FragmentParent(mol)
        parent_key = _safe_inchi(parent)
    except (RuntimeError, ValueError):
        parent_key = None
    try:
        formula = rdMolDescriptors.CalcMolFormula(mol)
    except (RuntimeError, ValueError):
        formula = None
    try:
        weight = float(Descriptors.MolWt(mol))
    except (RuntimeError, ValueError):
        weight = None
    if inchi_key:
        key, kind = f"inchikey:{inchi_key}", "inchikey"
    elif smiles:
        key, kind = f"smiles:{hashlib.sha256(smiles.encode()).hexdigest()}", "smiles"
    else:
        key, kind = f"molhash:{hashlib.sha256(Chem.MolToMolBlock(mol).encode()).hexdigest()}", "molhash"
    return Identity(
        key=key,
        kind=kind,
        canonical_smiles=smiles,
        inchi_key=inchi_key,
        parent_inchi_key=parent_key,
        formula=formula,
        molecular_weight=weight,
    )


def identity_from_smiles(smiles: str) -> Identity | None:
    mol = Chem.MolFromSmiles(smiles)
    return identity_from_mol(mol) if mol is not None else None


def _first_sdf_mol(path: Path) -> Chem.Mol | None:
    try:
        return mol_from_file(path, sanitize=True, removeHs=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _pdbqt_header_mol(path: Path) -> Chem.Mol | None:
    """Read Meeko's REMARK SMILES header from a PDBQT; no bond guessing."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        match = _SMILES_RE.match(line)
        if match:
            return Chem.MolFromSmiles(match.group(1))
    return None


def ligand_identity(path: str | Path) -> Identity:
    """Ligand identity from SDF/MOL/PDBQT, with content hash as last resort."""
    target = Path(path)
    mol = _first_sdf_mol(target) if target.suffix.lower() in {".sdf", ".mol"} else None
    if mol is None and target.suffix.lower() == ".pdbqt":
        mol = _pdbqt_header_mol(target)
    if mol is not None:
        return identity_from_mol(mol)
    return Identity(
        key=f"sha256:{content_sha256(target)}",
        kind="content",
    )


def receptor_identity(path: str | Path) -> Identity:
    target = Path(path)
    match = _PDB_ID.search(target.stem.lower())
    if match:
        pdb_id = match.group(1).upper()
        return Identity(key=f"pdb:{pdb_id}", kind="pdb")
    return Identity(key=f"sha256:{content_sha256(target)}", kind="content")


def identity_for_file(path: str | Path, kind_hint: str) -> Identity:
    if kind_hint == "receptor":
        return receptor_identity(path)
    return ligand_identity(path)


def identity_from_record(record: dict[str, Any]) -> Identity:
    """Identity for a provider/library record that already has a SMILES."""
    smiles = record.get("smiles") or record.get("canonicalSmiles")
    if isinstance(smiles, str):
        identity = identity_from_smiles(smiles)
        if identity is not None:
            return identity
    inchi_key = record.get("inchi_key") or record.get("inchiKey")
    if isinstance(inchi_key, str) and inchi_key:
        return Identity(key=f"inchikey:{inchi_key}", kind="inchikey", inchi_key=inchi_key)
    raise ValueError("record has neither a parseable SMILES nor an InChIKey")
