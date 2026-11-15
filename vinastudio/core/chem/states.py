"""Ligand-state enumeration: protonation, tautomers and stereoisomers.

Docking is conditional on the ligand state. This module produces a *list* of
chemically plausible states and never silently keeps only one; the preparation
layer prepares each state separately and the report records the policy.

Protonation needs the optional ``dimorphite_dl`` package (`uv sync --extra
states`). Tautomers and stereoisomers use RDKit; when the optional package is
absent and protonation was requested, the caller gets an actionable
``InvalidInputError`` rather than a silently reduced state set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rdkit import Chem

from vinastudio.core.errors import InvalidInputError

StateKind = Literal["input", "protonation", "tautomer", "stereo"]

DEFAULT_KINDS: tuple[StateKind, ...] = ("protonation", "tautomer", "stereo")
DEFAULT_PH_RANGE: tuple[float, float] = (7.0, 7.8)
DEFAULT_MAX_STATES = 8


@dataclass(frozen=True, slots=True)
class LigandState:
    state_id: str
    kind: StateKind
    smiles: str
    charge: int
    description: str

    def as_dict(self) -> dict[str, object]:
        return {
            "stateId": self.state_id,
            "kind": self.kind,
            "smiles": self.smiles,
            "charge": self.charge,
            "description": self.description,
        }


@dataclass(slots=True)
class StateEnumeration:
    states: list[LigandState] = field(default_factory=list)
    truncated: bool = False
    kinds: tuple[StateKind, ...] = DEFAULT_KINDS
    ph_range: tuple[float, float] = DEFAULT_PH_RANGE


def _canonical(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol, isomericSmiles=True, canonical=True)


def _validate(kinds: tuple[str, ...], ph_range: tuple[float, float], max_states: int) -> None:
    allowed = {"protonation", "tautomer", "stereo"}
    unknown = sorted(set(kinds) - allowed)
    if unknown:
        raise InvalidInputError(f"unknown ligand state kind(s): {', '.join(unknown)}")
    low, high = ph_range
    if not (0.0 <= low <= high <= 14.0):
        raise InvalidInputError(
            f"pH range must satisfy 0 <= min <= max <= 14, got {low!r}..{high!r}"
        )
    if max_states < 1:
        raise InvalidInputError("max_states must be at least 1")


def _protonation_smiles(smiles: str, ph_range: tuple[float, float]) -> list[str]:
    try:
        from dimorphite_dl import protonate_smiles
    except ImportError:
        try:
            # Older/newer releases have exposed the function from the
            # subpackage; keep both paths rather than pinning one layout.
            from dimorphite_dl.protonate import protonate_smiles
        except ImportError as exc:
            raise InvalidInputError(
                "protonation enumeration requires the optional 'states' extra "
                "(uv sync --extra states, dimorphite-dl)"
            ) from exc
    try:
        return list(
            protonate_smiles(
                smiles,
                ph_min=ph_range[0],
                ph_max=ph_range[1],
                precision=1.0,
            )
        )
    except Exception as exc:  # third-party chemistry can raise anything
        raise InvalidInputError(f"protonation enumeration failed: {exc}") from exc


def enumerate_states(
    mol: Chem.Mol,
    *,
    kinds: tuple[str, ...] = DEFAULT_KINDS,
    ph_range: tuple[float, float] = DEFAULT_PH_RANGE,
    max_states: int = DEFAULT_MAX_STATES,
) -> StateEnumeration:
    """Enumerate ligand states, always keeping the input state first."""
    _validate(kinds, ph_range, max_states)

    input_smiles = _canonical(mol)
    states: list[LigandState] = [
        LigandState(
            state_id="state-000",
            kind="input",
            smiles=input_smiles,
            charge=Chem.GetFormalCharge(mol),
            description="input structure",
        )
    ]
    seen = {input_smiles}
    truncated = False

    def add(smiles: str | None, kind: StateKind, description: str) -> None:
        nonlocal truncated
        if smiles is None:
            return
        candidate = Chem.MolFromSmiles(smiles)
        if candidate is None:
            return
        canonical = _canonical(candidate)
        if canonical in seen:
            return
        if len(states) >= max_states:
            truncated = True
            return
        seen.add(canonical)
        states.append(
            LigandState(
                state_id=f"state-{len(states):03d}",
                kind=kind,
                smiles=canonical,
                charge=Chem.GetFormalCharge(candidate),
                description=description,
            )
        )

    if "protonation" in kinds:
        for smiles in _protonation_smiles(input_smiles, ph_range):
            add(
                smiles,
                "protonation",
                f"protonation state at pH {ph_range[0]:g}-{ph_range[1]:g}",
            )

    if "tautomer" in kinds:
        from rdkit.Chem.MolStandardize import rdMolStandardize

        enumerator = rdMolStandardize.TautomerEnumerator()
        for tautomer in enumerator.Enumerate(mol):
            add(Chem.MolToSmiles(tautomer), "tautomer", "tautomer")

    if "stereo" in kinds:
        from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers

        for stereoisomer in EnumerateStereoisomers(mol):
            add(
                Chem.MolToSmiles(stereoisomer),
                "stereo",
                "stereoisomer",
            )

    return StateEnumeration(
        states=states,
        truncated=truncated,
        kinds=tuple(kinds),  # type: ignore[arg-type]
        ph_range=ph_range,
    )


def state_report(state: LigandState) -> dict[str, object]:
    """Wire-shaped state record used by preparation reports."""
    return state.as_dict()
