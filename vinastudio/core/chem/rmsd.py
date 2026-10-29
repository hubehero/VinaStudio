"""Heavy-atom RMSD of docked poses versus a reference ligand (redocking).

Answers the redocking question: did the search recover the crystallographic
binding mode? Industry convention treats RMSD < 2 Å as success — a convention,
not an absolute standard; the UI must say so.

Symmetry-corrected RMSD uses RDKit's ``rdMolAlign.CalcRMS``, which enumerates
automorphic atom mappings without superposing the two molecules. Docked poses
and the crystal reference are already in the receptor frame, so alignment must
not be used: a rigid-body shift is a different binding mode, not a perfect match.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdMolAlign

from vinastudio.core.chem.rdkit_io import mol_from_file
from vinastudio.core.errors import InvalidInputError

#: Community redocking convention, not a hard physical constant.
DEFAULT_RMSD_THRESHOLD = 2.0


def rmsd_vs_reference(
    poses_sdf: str,
    reference: Chem.Mol | str | Path,
    *,
    symmetrize: bool = True,
) -> list[float]:
    """RMSD of each ``$$$$``-separated pose against *reference* (heavy atoms).

    Parameters
    ----------
    poses_sdf:
        Multi-pose SDF text (``poses_to_sdf`` output).
    reference:
        Prepared reference ligand as an RDKit mol, SDF/MOL/PDB/MOL2 path, or
        PDBQT path (converted via the shared ``poses_to_sdf`` path).
    symmetrize:
        ``True`` (default) uses ``CalcRMS`` so symmetry-equivalent atom
        permutations do not inflate the score, while keeping the receptor frame.

    Returns
    -------
    One non-negative RMSD (Å) per pose, in file order.
    """
    ref = _heavy_only(_as_mol(reference))
    values: list[float] = []
    for record in _split_sdf(poses_sdf):
        pose = _heavy_only(_as_mol(record))
        values.append(_rmsd_one(pose, ref, symmetrize=symmetrize))
    return values


def rmsd_between(
    pose: Chem.Mol | str,
    reference: Chem.Mol | str,
    *,
    symmetrize: bool = True,
) -> float:
    """Heavy-atom RMSD between two molecules; copies internally.

    The public pairwise entry point: clustering must call this rather than
    re-implementing the no-superposition symmetry path a second time.
    """
    return _rmsd_one(
        _heavy_only(_as_mol(pose)),
        _heavy_only(_as_mol(reference)),
        symmetrize=symmetrize,
    )


def load_poses(poses_sdf: str) -> list[Chem.Mol]:
    """Heavy-atom molecule of each ``$$$$``-separated pose, in file order."""
    return [_heavy_only(_as_mol(record)) for record in _split_sdf(poses_sdf)]


def success_rate(values: Sequence[float], threshold: float = DEFAULT_RMSD_THRESHOLD) -> float:
    """Fraction of poses with RMSD < *threshold* (empty input → 0.0)."""
    if not values:
        return 0.0
    return sum(1 for v in values if v < threshold) / len(values)


def structure_matches(reference: Chem.Mol, other: Chem.Mol) -> bool | None:
    """Heavy-atom canonical SMILES equality, or ``None`` when either fails.

    Warn (never reject) when the uploaded reference is not the same chemical
    structure as the docked ligand — tautomer/protonation differences would
    silently inflate RMSD.
    """
    from vinastudio.core.chem.ligand_prep import _canonical_smiles

    a = _canonical_smiles(reference)
    b = _canonical_smiles(other)
    if a is None or b is None:
        return None
    return a == b


def reference_matches_poses(poses_sdf: str, reference: Chem.Mol | str | Path) -> bool | None:
    """Canonical-SMILES equality of *reference* vs the first pose.

    ``None`` means either side could not be canonicalised — unknown is not
    a mismatch, and callers must warn (never reject) on ``False``.
    """
    ref = _heavy_only(_as_mol(reference))
    pose = _heavy_only(_as_mol(_split_sdf(poses_sdf)[0]))
    return structure_matches(ref, pose)


# ── helpers ──────────────────────────────────────────────────────────────────


def _rmsd_one(pose: Chem.Mol, reference: Chem.Mol, *, symmetrize: bool) -> float:
    if pose.GetNumAtoms() != reference.GetNumAtoms():
        raise InvalidInputError(
            f"pose has {pose.GetNumAtoms()} heavy atoms, reference has "
            f"{reference.GetNumAtoms()} — cannot compute RMSD"
        )
    if pose.GetNumAtoms() == 0:
        return 0.0
    # Work on copies: later poses reuse the reference mol.
    prb = Chem.Mol(pose)
    ref = Chem.Mol(reference)
    try:
        if symmetrize:
            # CalcRMS is symmetry-aware but does not translate/rotate the probe.
            return float(rdMolAlign.CalcRMS(prb, ref))
        return _plain_rms(prb, ref)
    except (ValueError, RuntimeError) as exc:
        raise InvalidInputError(f"RMSD calculation failed: {exc}") from exc


def _plain_rms(a: Chem.Mol, b: Chem.Mol) -> float:
    ca, cb = a.GetConformer(), b.GetConformer()
    total = 0.0
    for i in range(a.GetNumAtoms()):
        pa, pb = ca.GetAtomPosition(i), cb.GetAtomPosition(i)
        total += (pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2 + (pa.z - pb.z) ** 2
    return (total / a.GetNumAtoms()) ** 0.5


def _heavy_only(mol: Chem.Mol) -> Chem.Mol:
    """Strip explicit hydrogens — redocking RMSD is heavy-atom by convention."""
    try:
        return Chem.RemoveHs(Chem.Mol(mol))
    except Exception:  # noqa: BLE001 - already-H-free or unsanitised input
        return mol


def _as_mol(source: Chem.Mol | str | Path) -> Chem.Mol:
    if isinstance(source, Chem.Mol):
        if source.GetNumConformers() == 0:
            raise InvalidInputError("molecule has no 3D coordinates")
        return source
    if isinstance(source, Path):
        return _mol_from_path(source)
    if isinstance(source, str):
        path = Path(source)
        if path.suffix.lower() in {".sdf", ".mol", ".pdbqt", ".pdb", ".mol2"} and path.is_file():
            return _mol_from_path(path)
        return _mol_from_sdf_text(source)
    raise TypeError(f"unsupported RMSD source: {type(source)!r}")


def _mol_from_path(path: Path) -> Chem.Mol:
    if not path.is_file():
        raise InvalidInputError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdbqt":
        return _mol_from_pdbqt_path(path)
    if suffix == ".sdf":
        mol = mol_from_file(path, removeHs=False)
        if mol is None:
            raise InvalidInputError(f"no readable molecule in {path}")
        if mol.GetNumConformers() == 0:
            raise InvalidInputError(f"no 3D coordinates in {path}")
        return mol
    if suffix == ".mol":
        mol = mol_from_file(path, removeHs=False)
        if mol is None:
            raise InvalidInputError(f"no readable molecule in {path}")
        return mol
    # .pdb / .mol2 — share the ligand-prep reader so formats stay in one place.
    from vinastudio.core.chem.ligand_prep import read_mol

    mol, _ = read_mol(path)
    if mol.GetNumConformers() == 0:
        raise InvalidInputError(f"no 3D coordinates in {path}")
    return mol


def _mol_from_pdbqt_path(path: Path) -> Chem.Mol:
    text = path.read_text(encoding="utf-8", errors="replace")
    from vinastudio.core.chem.export import poses_to_sdf

    try:
        sdf = poses_to_sdf(text, title_prefix="ref").sdf
    except (ImportError, RuntimeError, ValueError) as exc:
        raise InvalidInputError(f"could not convert PDBQT reference: {exc}") from exc
    return _mol_from_sdf_text(sdf)


def _mol_from_sdf_text(text: str) -> Chem.Mol:
    # Reuse pose_validation's normaliser: a blank header line shift makes
    # RDKit refuse the counts line.
    from vinastudio.core.chem.pose_validation import _normalize_molblock

    block = text.split("$$$$")[0] if "$$$$" in text else text
    mol = Chem.MolFromMolBlock(_normalize_molblock(block), removeHs=False, sanitize=False)
    if mol is None:
        raise InvalidInputError("could not parse reference as SDF/molblock")
    with contextlib.suppress(Chem.rdchem.AtomValenceException):
        Chem.SanitizeMol(mol)
    if mol.GetNumConformers() == 0:
        raise InvalidInputError("reference molecule has no 3D coordinates")
    return mol


def _split_sdf(text: str) -> list[str]:
    records = [part for part in text.split("$$$$") if part.strip()]
    if not records:
        raise InvalidInputError("poses SDF is empty")
    return records
