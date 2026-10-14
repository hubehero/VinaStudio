"""Drug-likeness descriptors for the properties panel (L2).

The values describe the input structure only; the Rule-of-Five verdict is a
rule of thumb over four of them, not a prediction of absorption or toxicity —
the panel footnote keeps that distinction visible.

Field names are camelCase because they are the wire contract
(``LigandProperties``): this module computes, the UI labels and formats.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Descriptors

from vinastudio.core.chem.pdbqt import _SMILES_RE


def compute_properties(mol: Chem.Mol) -> dict[str, float | int]:
    """Eight structure descriptors, keyed by their contract names.

    ``ringCount`` counts *aromatic* rings: the contract name and the panel
    label (「芳香环数」) both say so, while ``Descriptors.RingCount`` would
    also count aliphatic rings — a peptide macrocycle is not an aromatic ring.
    """
    return {
        "molWt": Descriptors.MolWt(mol),
        "molLogP": Descriptors.MolLogP(mol),
        "tpsa": Descriptors.TPSA(mol),
        "numHDonors": Descriptors.NumHDonors(mol),
        "numHAcceptors": Descriptors.NumHAcceptors(mol),
        "numRotatableBonds": Descriptors.NumRotatableBonds(mol),
        "ringCount": Descriptors.NumAromaticRings(mol),
        "qed": Descriptors.qed(mol),
    }


def lipinski_violations(props: dict[str, float | int]) -> int:
    """Count Rule-of-Five breaches; the original rule tolerates at most one.

    The panel reports the count (0–4) rather than a pass/fail flag, so a
    borderline molecule shows exactly which limit it crossed.
    """
    violations = 0
    if props["molWt"] > 500:
        violations += 1
    if props["molLogP"] > 5:
        violations += 1
    if props["numHDonors"] > 5:
        violations += 1
    if props["numHAcceptors"] > 10:
        violations += 1
    return violations


def descriptor_bundle(mol: Chem.Mol) -> dict[str, float | int]:
    """The three screening/batch columns for one molecule.

    Contract keys (TASK-13 §4.1/§4.6): library index rows and
    ``ligand_completed`` events carry exactly these, not the full
    eight-descriptor panel.
    """
    props = compute_properties(mol)
    return {
        "molWt": props["molWt"],
        "qed": props["qed"],
        "lipinskiViolations": lipinski_violations(props),
    }


def canonical_smiles(mol: Chem.Mol) -> str | None:
    # Mirrors ligand_prep._canonical_smiles: properties cannot import
    # ligand_prep (it imports us), so the rule is restated here.
    try:
        return Chem.MolToSmiles(Chem.RemoveHs(mol))
    except Exception:  # noqa: BLE001 - sanitisation can fail on odd input
        try:
            return Chem.MolToSmiles(mol)
        except Exception:  # noqa: BLE001
            return None


def _read_source_mol(path: Path) -> Chem.Mol | None:
    """First readable record of a source structure file, or None.

    ``.pdbqt`` returns None on purpose: it carries no bond orders, so its
    profile comes from the Meeko header SMILES instead (see ligand_profile).
    """
    try:
        suffix = path.suffix.lower()
        if suffix == ".sdf":
            supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=True)
            return next((mol for mol in supplier if mol is not None), None)
        if suffix == ".mol":
            return Chem.MolFromMolFile(str(path), removeHs=False, sanitize=True)
        if suffix == ".mol2":
            return Chem.MolFromMol2File(str(path), removeHs=False, sanitize=True)
        if suffix == ".pdb":
            return Chem.MolFromPDBFile(str(path), removeHs=False, sanitize=True)
        return None
    except Exception:  # noqa: BLE001 - best-effort path, absence is not an error
        return None


def _header_mol(text: str) -> Chem.Mol | None:
    """Molecule rebuilt from a prepared PDBQT's ``REMARK SMILES`` header."""
    for line in text.splitlines():
        match = _SMILES_RE.match(line)
        if match:
            mol = Chem.MolFromSmiles(match.group(1))
            if mol is not None:
                return mol
            return None
    return None


def ligand_profile(
    source_path: str | Path | None = None,
    *,
    pdbqt_path: str | Path | None = None,
    pdbqt_text: str | None = None,
) -> dict[str, float | int | str | None]:
    """Best-effort ``(smiles, molWt, qed, lipinskiViolations)`` for a ligand.

    Source structure file wins over the prepared PDBQT (TASK-13 §4.6): a
    PDBQT rebuilds chemistry from one header SMILES, so it is the fallback.
    Every field stays None when nothing parses — the caller reports nulls
    rather than failing the docking run that produced the request.
    """
    out: dict[str, float | int | str | None] = {
        "smiles": None,
        "molWt": None,
        "qed": None,
        "lipinskiViolations": None,
    }

    mol: Chem.Mol | None = None
    if source_path is not None:
        mol = _read_source_mol(Path(source_path))
    if mol is None:
        try:
            if pdbqt_text is None and pdbqt_path is not None:
                pdbqt_text = Path(pdbqt_path).read_text(
                    encoding="utf-8", errors="ignore"
                )
            if pdbqt_text is not None:
                mol = _header_mol(pdbqt_text)
        except OSError:
            mol = None
    if mol is None:
        return out

    out["smiles"] = canonical_smiles(mol)
    # Exotic structures must not fail the run that asked for a profile.
    with suppress(Exception):
        out.update(descriptor_bundle(mol))
    return out
