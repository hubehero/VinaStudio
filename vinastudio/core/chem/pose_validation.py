"""Geometric health-check for docked poses (PoseBusters subset, offline).

Scoring functions report binding energy, not whether the geometry is chemically
sane. This module runs six independent, report-only checks on a pose and returns
:class:`Finding` entries; it never modifies coordinates. Thresholds live in one
dict so they can be tuned (and shown in the UI) in one place.

Checks that compare against a reference assume the reference is the prepared
ligand SDF the user already accepted — chirality and planarity are judged
against that structure, not against idealised templates.
"""

from __future__ import annotations

import contextlib
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdCIPLabeler

from vinastudio.core.chem.rdkit_io import mol_from_file
from vinastudio.core.errors import InvalidInputError

type Severity = Literal["error", "warning"]

#: Every threshold the checks use, in Å / degrees. Kept together so the UI can
#: display the same numbers the code applied.
THRESHOLDS: dict[str, float] = {
    "internal_clash": 0.65,  # fraction of the sum of vdW radii
    "bond_length": 0.45,  # Å vs reference
    "angle": 25.0,  # degrees vs reference
    "planarity": 0.1,  # Å RMSD from best-fit plane
    "out_of_box": 2.0,  # Å outside center ± size/2
}

#: Check codes. Each can be switched off via ``enabled``.
CHECK_CODES: frozenset[str] = frozenset(
    {
        "internal_clash",
        "bond_length_outlier",
        "angle_outlier",
        "planarity_break",
        "chirality_flip",
        "out_of_box",
    }
)

#: i18n key prefix; locales spell out the human sentence per code.
MESSAGE_KEY_PREFIX = "poseCheck."

#: Max concrete examples packed into one finding's detail (keeps payloads small).
_MAX_EXAMPLES = 5


@dataclass(frozen=True, slots=True)
class Finding:
    """One reported issue. ``detail`` carries measured values for the UI."""

    code: str
    severity: Severity
    message_key: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message_key": self.message_key,
            "detail": self.detail,
        }


def validate_pose(
    pose: Chem.Mol | str | Path,
    reference: Chem.Mol | str | Path | None = None,
    *,
    box: Any | None = None,
    enabled: Collection[str] | None = None,
) -> list[Finding]:
    """Run the enabled geometric checks on one pose.

    Parameters
    ----------
    pose:
        Docked geometry as an RDKit mol, SDF text/path, or PDBQT text/path
        (converted via the existing ``poses_to_sdf`` path).
    reference:
        Prepared (not docked) ligand with 3D coordinates. ``None`` skips the
        four reference-relative checks; clash and box checks still run.
    box:
        ``core.box.Box`` or any object with ``center`` / ``size`` sequences.
        ``None`` skips ``out_of_box``.
    enabled:
        Subset of :data:`CHECK_CODES` to run. ``None`` runs all six.
    """
    pose_mol = _as_mol(pose)
    active = _active_checks(enabled)
    findings: list[Finding] = []

    if "internal_clash" in active:
        findings.extend(_check_internal_clash(pose_mol))
    if "out_of_box" in active and box is not None:
        findings.extend(_check_out_of_box(pose_mol, box))
    if reference is not None:
        ref_mol = _as_mol(reference)
        match = _atom_map(pose_mol, ref_mol)
        if match is None:
            if "bond_length_outlier" in active or "angle_outlier" in active:
                findings.append(
                    Finding(
                        code="reference_unmatched",
                        severity="error",
                        message_key=f"{MESSAGE_KEY_PREFIX}reference_unmatched",
                        detail={
                            "poseAtoms": pose_mol.GetNumAtoms(),
                            "referenceAtoms": ref_mol.GetNumAtoms(),
                        },
                    )
                )
        else:
            if "bond_length_outlier" in active:
                findings.extend(_check_bond_lengths(pose_mol, ref_mol, match))
            if "angle_outlier" in active:
                findings.extend(_check_angles(pose_mol, ref_mol, match))
            if "planarity_break" in active:
                findings.extend(_check_planarity(pose_mol, ref_mol, match))
            if "chirality_flip" in active:
                findings.extend(_check_chirality(pose_mol, ref_mol, match))
    return findings


def validate_poses(
    sdf: str,
    reference: Chem.Mol | str | Path | None = None,
    *,
    box: Any | None = None,
    enabled: Collection[str] | None = None,
) -> list[list[Finding]]:
    """Validate each ``$$$$``-separated record in a multi-pose SDF."""
    records = _split_sdf(sdf)
    return [
        validate_pose(record, reference, box=box, enabled=enabled) for record in records
    ]


def worst_severity(findings: Iterable[Finding]) -> Severity | None:
    """Highest severity in the list, or ``None`` when there are no findings."""
    severities = {f.severity for f in findings}
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return None


# ── helpers ──────────────────────────────────────────────────────────────────


def _active_checks(enabled: Collection[str] | None) -> frozenset[str]:
    if enabled is None:
        return CHECK_CODES
    unknown = set(enabled) - CHECK_CODES
    if unknown:
        raise ValueError(f"unknown pose check(s): {sorted(unknown)}")
    return frozenset(enabled)


def _finding(code: str, severity: Severity, detail: dict[str, Any]) -> Finding:
    # Resolve the threshold key from the code so every finding can echo it.
    threshold_key = {
        "internal_clash": "internal_clash",
        "bond_length_outlier": "bond_length",
        "angle_outlier": "angle",
        "planarity_break": "planarity",
        "out_of_box": "out_of_box",
    }.get(code)
    payload = dict(detail)
    if threshold_key is not None:
        payload.setdefault("threshold", THRESHOLDS[threshold_key])
    return Finding(
        code=code,
        severity=severity,
        message_key=f"{MESSAGE_KEY_PREFIX}{code}",
        detail=payload,
    )


def _as_mol(source: Chem.Mol | str | Path) -> Chem.Mol:
    """Accept an RDKit mol, SDF text/path, or PDBQT text/path."""
    if isinstance(source, Chem.Mol):
        if source.GetNumConformers() == 0:
            raise InvalidInputError("pose molecule has no 3D coordinates")
        return source
    if isinstance(source, Path):
        return _mol_from_path(source)
    if isinstance(source, str):
        if Path(source).suffix.lower() in {".sdf", ".mol"} and "\n" not in source.strip()[:80]:
            path = Path(source)
            if path.is_file():
                return _mol_from_path(path)
        return _mol_from_text(source)
    raise TypeError(f"unsupported pose source: {type(source)!r}")


def _mol_from_path(path: Path) -> Chem.Mol:
    if not path.is_file():
        raise InvalidInputError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdbqt":
        return _mol_from_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".sdf":
        mol = mol_from_file(path, removeHs=False)
        if mol is None:
            raise InvalidInputError(f"no readable molecule in {path}")
        return mol
    if suffix == ".mol":
        mol = mol_from_file(path, removeHs=False)
        if mol is None:
            raise InvalidInputError(f"no readable molecule in {path}")
        return mol
    raise InvalidInputError(f"unsupported pose file type: {suffix or path.name}")


def _mol_from_text(text: str) -> Chem.Mol:
    stripped = text.lstrip()
    if (
        stripped.startswith("ROOT")
        or "\nROOT" in text
        or (stripped.startswith("REMARK") and "TORSDOF" in text)
    ):
        return _mol_from_pdbqt(text)
    # Keep the record body intact: strip() would eat the blank molblock header
    # line and shift every subsequent column.
    block = text.split("$$$$")[0] if "$$$$" in text else text
    mol = Chem.MolFromMolBlock(
        _normalize_molblock(block), removeHs=False, sanitize=False
    )
    if mol is None:
        raise InvalidInputError("could not parse pose as SDF/molblock")
    with contextlib.suppress(Chem.rdchem.AtomValenceException):
        # Docked coordinates are not always sanitisable; geometry checks still
        # work on the graph we already have.
        Chem.SanitizeMol(mol)
    if mol.GetNumConformers() == 0:
        raise InvalidInputError("pose molecule has no 3D coordinates")
    return mol


def _normalize_molblock(block: str) -> str:
    """Put the counts line back on line 4 (index 3).

    Joining ``$$$$``-separated records with an extra blank line shifts the
    header so RDKit reads an empty counts line and refuses the block.
    """
    lines = block.splitlines()
    for index, line in enumerate(lines[:12]):
        if "V2000" in line or "V3000" in line:
            if index > 3:
                # Keep exactly three header lines (name, program, comment).
                lines = lines[index - 3 :]
            elif index < 3:
                lines = [""] * (3 - index) + lines
            return "\n".join(lines) + "\n"
    return block


def _mol_from_pdbqt(text: str) -> Chem.Mol:
    from vinastudio.core.chem.export import poses_to_sdf

    sdf = poses_to_sdf(text).sdf
    return _mol_from_text(sdf)


def _split_sdf(sdf: str) -> list[str]:
    """Split a multi-record SDF, preserving each molblock's header lines."""
    records: list[str] = []
    for part in sdf.split("$$$$"):
        body = part.rstrip()
        if not body.strip():
            continue
        records.append(body + "\n")
    return records


def _atom_map(pose: Chem.Mol, reference: Chem.Mol) -> list[int] | None:
    """Pose atom index for each reference atom, or ``None`` when unmatched."""
    match = pose.GetSubstructMatch(reference, useChirality=False)
    if len(match) == reference.GetNumAtoms():
        return list(match)
    # Same graph, possibly written with different atom ordering conventions.
    match = reference.GetSubstructMatch(pose, useChirality=False)
    if len(match) == pose.GetNumAtoms() and pose.GetNumAtoms() == reference.GetNumAtoms():
        inverse = [0] * len(match)
        for pose_idx, ref_idx in enumerate(match):
            inverse[ref_idx] = pose_idx
        return inverse
    return None


def _coords(mol: Chem.Mol) -> np.ndarray:
    return np.asarray(mol.GetConformer().GetPositions(), dtype=float)


# ── individual checks ────────────────────────────────────────────────────────


def _check_internal_clash(mol: Chem.Mol) -> list[Finding]:
    """Non-bonded pairs closer than ``scale × (vdW_i + vdW_j)``.

    1-2 and 1-3 pairs are excluded. A clash across a rotatable 1-4 path is a
    warning (torsional strain is plausible); everything else is an error.
    """
    n = mol.GetNumAtoms()
    if n < 2:
        return []
    coords = _coords(mol)
    topo = Chem.GetDistanceMatrix(mol)
    pt = Chem.GetPeriodicTable()
    vdw = np.array([pt.GetRvdw(atom.GetAtomicNum()) for atom in mol.GetAtoms()])
    limit = THRESHOLDS["internal_clash"] * (vdw[:, None] + vdw[None, :])

    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.linalg.norm(diff, axis=-1)

    upper = np.triu(np.ones((n, n), dtype=bool), k=1)
    # topo == 0 is self; 1–2 and 1–3 are covalently constrained.
    close = upper & (dist < limit) & (topo > 2)
    if not close.any():
        return []

    pairs = np.argwhere(close)
    examples: list[dict[str, Any]] = []
    has_error = False
    for i, j in pairs:
        rotatable_14 = bool(topo[i, j] == 3 and _rotatable_path(mol, int(i), int(j)))
        if not rotatable_14:
            has_error = True
        if len(examples) < _MAX_EXAMPLES:
            examples.append(
                {
                    "atoms": [int(i), int(j)],
                    "distance": round(float(dist[i, j]), 3),
                    "limit": round(float(limit[i, j]), 3),
                    "topologicalDistance": int(topo[i, j]),
                    "rotatable14": rotatable_14,
                }
            )
    severity: Severity = "error" if has_error else "warning"
    return [
        _finding(
            "internal_clash",
            severity,
            {"count": len(pairs), "examples": examples},
        )
    ]


def _rotatable_path(mol: Chem.Mol, i: int, k: int) -> bool:
    """Whether a 1-4 path i–j–mid–k crosses a single, non-ring bond."""
    for j_atom in mol.GetAtomWithIdx(i).GetNeighbors():
        j = j_atom.GetIdx()
        if j == k:
            continue
        for mid_atom in mol.GetAtomWithIdx(j).GetNeighbors():
            mid = mid_atom.GetIdx()
            if mid in (i, j):
                continue
            bond = mol.GetBondBetweenAtoms(j, mid)
            if bond is None:
                continue
            if not any(n.GetIdx() == k for n in mol.GetAtomWithIdx(mid).GetNeighbors()):
                continue
            return bond.GetBondType() == Chem.BondType.SINGLE and not bond.IsInRing()
    return False


def _check_out_of_box(mol: Chem.Mol, box: Any) -> list[Finding]:
    center = np.asarray(tuple(box.center), dtype=float)
    size = np.asarray(tuple(box.size), dtype=float)
    half = size / 2.0
    overflow = np.maximum(np.abs(_coords(mol) - center) - half, 0.0)
    outside = np.linalg.norm(overflow, axis=1)
    worst = int(np.argmax(outside))
    if float(outside[worst]) <= THRESHOLDS["out_of_box"]:
        return []
    offenders = np.nonzero(outside > THRESHOLDS["out_of_box"])[0]
    return [
        _finding(
            "out_of_box",
            "error",
            {
                "count": len(offenders),
                "worstAtom": worst,
                "distance": round(float(outside[worst]), 3),
                "atoms": [int(a) for a in offenders[:_MAX_EXAMPLES]],
            },
        )
    ]


def _check_bond_lengths(
    pose: Chem.Mol, reference: Chem.Mol, match: list[int]
) -> list[Finding]:
    ref_coords = _coords(reference)
    pose_coords = _coords(pose)
    worst_delta = 0.0
    examples: list[dict[str, Any]] = []
    count = 0
    for bond in reference.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        ref_len = float(np.linalg.norm(ref_coords[a] - ref_coords[b]))
        pose_len = float(np.linalg.norm(pose_coords[match[a]] - pose_coords[match[b]]))
        delta = abs(pose_len - ref_len)
        if delta > THRESHOLDS["bond_length"]:
            count += 1
            worst_delta = max(worst_delta, delta)
            if len(examples) < _MAX_EXAMPLES:
                examples.append(
                    {
                        "referenceAtoms": [a, b],
                        "delta": round(delta, 3),
                        "referenceLength": round(ref_len, 3),
                        "poseLength": round(pose_len, 3),
                    }
                )
    if count == 0:
        return []
    return [
        _finding(
            "bond_length_outlier",
            "error",
            {"count": count, "worstDelta": round(worst_delta, 3), "examples": examples},
        )
    ]


def _check_angles(pose: Chem.Mol, reference: Chem.Mol, match: list[int]) -> list[Finding]:
    worst_delta = 0.0
    examples: list[dict[str, Any]] = []
    count = 0
    for center in reference.GetAtoms():
        neighbors = [n.GetIdx() for n in center.GetNeighbors()]
        c_idx = center.GetIdx()
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                a, b = neighbors[i], neighbors[j]
                ref_angle = _angle_deg(reference, a, c_idx, b)
                pose_angle = _angle_deg(pose, match[a], match[c_idx], match[b])
                delta = abs(pose_angle - ref_angle)
                if delta > THRESHOLDS["angle"]:
                    count += 1
                    worst_delta = max(worst_delta, delta)
                    if len(examples) < _MAX_EXAMPLES:
                        examples.append(
                            {
                                "referenceAtoms": [a, c_idx, b],
                                "delta": round(delta, 2),
                                "referenceAngle": round(ref_angle, 2),
                                "poseAngle": round(pose_angle, 2),
                            }
                        )
    if count == 0:
        return []
    return [
        _finding(
            "angle_outlier",
            "error",
            {"count": count, "worstDelta": round(worst_delta, 2), "examples": examples},
        )
    ]


def _angle_deg(mol: Chem.Mol, i: int, j: int, k: int) -> float:
    conf = mol.GetConformer()
    b = np.asarray(conf.GetAtomPosition(j))
    a = np.asarray(conf.GetAtomPosition(i)) - b
    c = np.asarray(conf.GetAtomPosition(k)) - b
    denom = float(np.linalg.norm(a) * np.linalg.norm(c))
    if denom == 0.0:
        return 0.0
    cos = float(np.clip(np.dot(a, c) / denom, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def _planar_groups(reference: Chem.Mol) -> list[list[int]]:
    """Aromatic rings and double-bond heavy-atom systems from the reference."""
    groups: list[list[int]] = []
    for ring in reference.GetRingInfo().AtomRings():
        if len(ring) >= 5 and all(
            reference.GetAtomWithIdx(i).GetIsAromatic() for i in ring
        ):
            groups.append(list(ring))
    for bond in reference.GetBonds():
        if bond.GetBondType() != Chem.BondType.DOUBLE:
            continue
        atoms = {bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()}
        for idx in tuple(atoms):
            for nbr in reference.GetAtomWithIdx(idx).GetNeighbors():
                if nbr.GetAtomicNum() != 1:
                    atoms.add(nbr.GetIdx())
        if len(atoms) >= 3:
            groups.append(sorted(atoms))
    return groups


def _check_planarity(
    pose: Chem.Mol, reference: Chem.Mol, match: list[int]
) -> list[Finding]:
    pose_coords = _coords(pose)
    worst_rmsd = 0.0
    examples: list[dict[str, Any]] = []
    count = 0
    for group in _planar_groups(reference):
        pts = pose_coords[[match[i] for i in group]]
        rmsd = _plane_rmsd(pts)
        if rmsd > THRESHOLDS["planarity"]:
            count += 1
            worst_rmsd = max(worst_rmsd, rmsd)
            if len(examples) < _MAX_EXAMPLES:
                examples.append(
                    {
                        "referenceAtoms": group,
                        "rmsd": round(rmsd, 3),
                    }
                )
    if count == 0:
        return []
    return [
        _finding(
            "planarity_break",
            "error",
            {"count": count, "worstRmsd": round(worst_rmsd, 3), "examples": examples},
        )
    ]


def _plane_rmsd(points: np.ndarray) -> float:
    """RMSD of points from their best-fit plane (smallest singular value)."""
    if len(points) < 3:
        return 0.0
    centered = points - points.mean(axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    # Three singular values for 3D points; the last measures out-of-plane spread.
    return float(np.sqrt((singular[-1] ** 2) / len(points)))


def _cip_labels(mol: Chem.Mol) -> dict[int, str]:
    Chem.AssignStereochemistryFrom3D(mol)
    rdCIPLabeler.AssignCIPLabels(mol)
    labels: dict[int, str] = {}
    for atom in mol.GetAtoms():
        if atom.HasProp("_CIPCode"):
            labels[atom.GetIdx()] = atom.GetProp("_CIPCode")
    return labels


def _check_chirality(
    pose: Chem.Mol, reference: Chem.Mol, match: list[int]
) -> list[Finding]:
    ref_labels = _cip_labels(reference)
    pose_labels = _cip_labels(pose)
    mismatches: list[dict[str, Any]] = []
    for ref_idx, label in sorted(ref_labels.items()):
        pose_idx = match[ref_idx]
        pose_label = pose_labels.get(pose_idx)
        if pose_label != label:
            mismatches.append(
                {
                    "referenceAtom": ref_idx,
                    "poseAtom": pose_idx,
                    "referenceCip": label,
                    "poseCip": pose_label,
                }
            )
    if not mismatches:
        return []
    return [
        _finding(
            "chirality_flip",
            "error",
            {
                "count": len(mismatches),
                "examples": mismatches[:_MAX_EXAMPLES],
            },
        )
    ]
