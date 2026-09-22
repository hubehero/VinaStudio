"""Interaction analysis endpoints for protein-ligand complexes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from vinastudio.core.chem.autodock_types import element_for
from vinastudio.core.errors import InvalidInputError, VinaStudioError, brief_error

log = logging.getLogger(__name__)

router = APIRouter(prefix="/interactions", tags=["interactions"])

#: Contact thresholds in Angstrom, applied per interaction type.  The caller's
#: ``distanceCutoff`` decides how far to look; these decide what a contact is
#: called, so a search radius can never silently disable a rule.
HYDROGEN_BOND_MAX_DISTANCE = 3.5
HYDROPHOBIC_MAX_DISTANCE = 4.0
IONIC_MAX_DISTANCE = 4.0

#: The widest rule above, so the default radius starves nothing.
DEFAULT_DISTANCE_CUTOFF = 4.0

#: Elements that take part in the contacts reported here.  Carbon is required
#: for hydrophobic contacts; hydrogens and metals are not contacts.
INTERACTION_ELEMENTS = frozenset({"C", "N", "O", "S", "F", "Cl", "Br"})

_POLAR_ELEMENTS = frozenset({"N", "O"})
_HYDROPHOBIC_ELEMENTS = frozenset({"C", "S"})

#: Side-chain atoms that carry a formal charge at physiological pH.  Only
#: geometry is available, so a salt bridge is reported when a contact involves
#: one of these; the rule reads residue and atom names, which PDB and PDBQT
#: both carry, so the two input formats agree.
CHARGED_SIDECHAIN_ATOMS = frozenset({
    ("ASP", "OD1"),
    ("ASP", "OD2"),
    ("GLU", "OE1"),
    ("GLU", "OE2"),
    ("LYS", "NZ"),
    ("ARG", "NE"),
    ("ARG", "NH1"),
    ("ARG", "NH2"),
})


@router.post("/analyze")
def analyze_interactions(request: dict[str, Any]) -> dict[str, Any]:
    """Analyze protein-ligand interactions from PDBQT or SDF files.

    This is a simplified analysis that identifies potential interactions
    based on distance and atom types. For more accurate analysis, use
    tools like PLIP or FPocket.
    """
    receptor_path = request.get("receptorPath", "")
    ligand_path = request.get("ligandPath", "")
    ligand_pdbqt = request.get("ligandPdbqtString", "")
    distance_cutoff = request.get("distanceCutoff", DEFAULT_DISTANCE_CUTOFF)

    # The receptor is never optional: the old first check also accepted a bare
    # ligand and silently reported "no interactions" for a contact analysis
    # with no protein in it.
    if not receptor_path:
        raise InvalidInputError("receptorPath is required")

    if not ligand_path and not ligand_pdbqt:
        raise InvalidInputError("ligandPath or ligandPdbqtString is required")

    try:
        interactions = _find_interactions(
            receptor_path=receptor_path,
            ligand_path=ligand_path,
            ligand_pdbqt=ligand_pdbqt,
            distance_cutoff=distance_cutoff,
        )
        return {
            "interactions": interactions,
            "count": len(interactions),
        }
    except VinaStudioError:
        raise
    except Exception as e:
        log.exception("Failed to analyze interactions")
        raise InvalidInputError(f"failed to analyze interactions: {brief_error(e)}") from e


def _find_interactions(
    receptor_path: str = "",
    ligand_path: str = "",
    ligand_pdbqt: str = "",
    distance_cutoff: float = DEFAULT_DISTANCE_CUTOFF,
) -> list[dict[str, Any]]:
    """Find interactions between receptor and ligand atoms."""
    import numpy as np

    # Parse receptor atoms
    receptor_atoms = _parse_receptor_atoms(receptor_path) if receptor_path else []

    # Parse ligand atoms
    ligand_atoms = _parse_ligand_atoms(ligand_path, ligand_pdbqt)

    interactions = []

    for r_atom in receptor_atoms:
        for l_atom in ligand_atoms:
            dx = r_atom["x"] - l_atom["x"]
            dy = r_atom["y"] - l_atom["y"]
            dz = r_atom["z"] - l_atom["z"]
            dist = np.sqrt(dx * dx + dy * dy + dz * dz)

            if dist <= distance_cutoff:
                inter_type = _classify_interaction(r_atom, l_atom, dist)
                if inter_type:
                    interactions.append({
                        "type": inter_type,
                        "receptorResidue": r_atom.get("residue", ""),
                        "receptorChain": r_atom.get("chain", ""),
                        "receptorResSeq": r_atom.get("resSeq", ""),
                        "receptorAtom": r_atom.get("atom", ""),
                        "receptorX": r_atom["x"],
                        "receptorY": r_atom["y"],
                        "receptorZ": r_atom["z"],
                        "ligandAtom": l_atom.get("atom", ""),
                        "ligandX": l_atom["x"],
                        "ligandY": l_atom["y"],
                        "ligandZ": l_atom["z"],
                        "distance": round(dist, 2),
                    })

    # Sort by distance
    interactions.sort(key=lambda x: x["distance"])

    return interactions


def _parse_receptor_atoms(path: str) -> list[dict[str, Any]]:
    """Parse receptor atoms from PDB or PDBQT file.

    A file that cannot be read is an error, not an empty contact list: the old
    silent fallback made a broken path look like "no interactions detected".
    """
    atoms = []
    parsed = 0
    # Preparation writes `.pdbqt`; the column the element lives in depends on it.
    is_pdbqt = path.endswith(".pdbqt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(("ATOM", "HETATM")):
                    atom = _parse_pdb_atom(line, is_pdbqt=is_pdbqt)
                    if atom:
                        parsed += 1
                        if atom["element"] in INTERACTION_ELEMENTS:
                            atoms.append(atom)
    except OSError as exc:
        raise InvalidInputError(f"cannot read receptor file {path}: {brief_error(exc)}") from exc
    except UnicodeDecodeError as exc:
        raise InvalidInputError(
            f"receptor file {path} is not UTF-8 text: {brief_error(exc)}"
        ) from exc
    if parsed == 0:
        raise InvalidInputError(f"no ATOM/HETATM records found in receptor file {path}")
    return atoms


def _parse_ligand_atoms(path: str = "", pdbqt_string: str = "") -> list[dict[str, Any]]:
    """Parse ligand atoms from SDF, PDBQT, or string."""
    atoms = []

    if pdbqt_string:
        atoms = _parse_pdbqt_atoms(pdbqt_string)
    elif path:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if path.endswith(".pdbqt"):
                atoms = _parse_pdbqt_atoms(content)
            elif path.endswith(".sdf"):
                atoms = _parse_sdf_atoms(content)
        except OSError as exc:
            raise InvalidInputError(f"cannot read ligand file {path}: {brief_error(exc)}") from exc
        except UnicodeDecodeError as exc:
            raise InvalidInputError(
                f"ligand file {path} is not UTF-8 text: {brief_error(exc)}"
            ) from exc

    if not atoms:
        source = path or "ligandPdbqtString"
        raise InvalidInputError(f"no atoms could be parsed from {source}")
    return atoms


def _parse_pdb_atom(line: str, *, is_pdbqt: bool) -> dict[str, Any] | None:
    """Parse a PDB or PDBQT ATOM/HETATM line.

    Columns 77-78 hold the element symbol in a PDB file and the AutoDock atom
    type in a PDBQT file, where a type may be two characters wide (``OA``,
    ``NA``, ``HD``, ``SA``).  Reading that column as a symbol gave aromatic
    carbons (type ``A``) the element ``A``, so every hydrophobic contact built
    on an aromatic ring was dropped from PDBQT input.
    """
    try:
        x = float(line[30:38])
        y = float(line[38:46])
        z = float(line[46:54])
        atom = line[12:16].strip()
        residue = line[17:20].strip()
        # Chain and sequence number, without which same-named residues in the
        # contact table are indistinguishable (ILE, ILE, ILE...).
        chain = line[21:22].strip()
        res_seq = line[22:26].strip()
        # The type/element field runs to the end of the record.
        column = line[76:].strip() if len(line) > 76 else ""

        if is_pdbqt:
            element = element_for(atom, column)
        else:
            element = column.capitalize() if column else element_for(atom, "")

        return {
            "x": x,
            "y": y,
            "z": z,
            "atom": atom,
            "residue": residue,
            "chain": chain,
            "resSeq": res_seq,
            "element": element,
            "charged": (residue, atom) in CHARGED_SIDECHAIN_ATOMS,
        }
    except (ValueError, IndexError):
        return None


def _parse_pdbqt_atoms(content: str) -> list[dict[str, Any]]:
    """Parse atoms from PDBQT content."""
    atoms = []
    for line in content.split("\n"):
        if line.startswith(("ATOM", "HETATM")):
            atom = _parse_pdb_atom(line, is_pdbqt=True)
            if atom:
                atoms.append(atom)
    return atoms


def _parse_sdf_atoms(content: str) -> list[dict[str, Any]]:
    """Parse atoms from SDF content."""
    atoms = []
    lines = content.split("\n")

    # Find the counts line (line 4)
    if len(lines) < 5:
        return atoms

    try:
        counts = lines[3].split()
        n_atoms = int(counts[0])
    except (ValueError, IndexError):
        return atoms

    # Parse atoms block (starts at line 4)
    for i in range(4, min(4 + n_atoms, len(lines))):
        parts = lines[i].split()
        if len(parts) >= 4:
            try:
                x = float(parts[0])
                y = float(parts[1])
                z = float(parts[2])
                element = parts[3].capitalize()

                if element in INTERACTION_ELEMENTS:
                    atoms.append({
                        "x": x,
                        "y": y,
                        "z": z,
                        "atom": element,
                        "residue": "LIG",
                        "element": element,
                    })
            except (ValueError, IndexError):
                continue

    return atoms


def _classify_interaction(
    receptor: dict[str, Any],
    ligand: dict[str, Any],
    distance: float,
) -> str | None:
    """Name the contact between two atoms, or ``None`` when there is none.

    Salt bridges are tested first: a charged side chain within the hydrogen-bond
    window is the same geometry described more specifically.  Every threshold is
    per type, so widening the search radius can only add contacts, never change
    what an existing one is called.
    """
    r_element = receptor["element"]
    l_element = ligand["element"]

    # Ionic interactions: a charged receptor side chain facing a polar ligand atom
    if (
        receptor.get("charged")
        and r_element in _POLAR_ELEMENTS
        and l_element in _POLAR_ELEMENTS
        and distance < IONIC_MAX_DISTANCE
    ):
        return "ionic"

    # Hydrogen bonds: N-O, N-N, O-O with distance < 3.5
    if (
        r_element in _POLAR_ELEMENTS
        and l_element in _POLAR_ELEMENTS
        and distance < HYDROGEN_BOND_MAX_DISTANCE
    ):
        return "hydrogen_bond"

    # Hydrophobic contacts: C-C, C-S with distance < 4.0
    if (
        r_element in _HYDROPHOBIC_ELEMENTS
        and l_element in _HYDROPHOBIC_ELEMENTS
        and "C" in (r_element, l_element)
        and distance < HYDROPHOBIC_MAX_DISTANCE
    ):
        return "hydrophobic"

    return None
