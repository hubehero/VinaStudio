"""Interaction fingerprints: contact geometry, encoding, similarity, clustering.

Contact parsing and classification were migrated verbatim from
``vinastudio/server/routers/interactions.py`` — the HTTP analyze endpoint
delegates here so one implementation serves the wire contract, docking jobs
and batch grouping (TASK-16).  The wire contract is unchanged; the only
behavioural fixes are first-model PDBQT parsing and the insertion-code
column the fingerprint residue keys need (task book勘误 ①②).
"""

from __future__ import annotations

from typing import Any

from vinastudio.core.chem.autodock_types import element_for
from vinastudio.core.chem.pdb_lines import WATER_RESIDUES
from vinastudio.core.errors import InvalidInputError, brief_error

#: Contact thresholds in Angstrom, applied per interaction type.  The caller's
#: ``distanceCutoff`` decides how far to look; these decide what a contact is
#: called, so a search radius can never silently disable a rule.
HYDROGEN_BOND_MAX_DISTANCE = 3.5
HYDROPHOBIC_MAX_DISTANCE = 4.0
IONIC_MAX_DISTANCE = 4.0
HALOGEN_BOND_MAX_DISTANCE = 3.5
METAL_COORDINATION_MAX_DISTANCE = 3.0
WATER_MEDIATED_MAX_DISTANCE = 3.5

#: The widest rule above, so the default radius starves nothing.
DEFAULT_DISTANCE_CUTOFF = 4.0

#: Elements that take part in the contacts reported here.  Carbon is required
#: for hydrophobic contacts; hydrogens are not contacts.  Metals are parsed
#: separately so they can be reported as coordination, never as hydrophobic.
INTERACTION_ELEMENTS = frozenset({"C", "N", "O", "S", "F", "Cl", "Br", "I"})
METAL_ELEMENTS = frozenset({"Mg", "Mn", "Zn", "Ca", "Fe", "Cu", "Ni", "Co", "Cd", "Hg"})
HALOGEN_ELEMENTS = frozenset({"F", "Cl", "Br", "I"})
WATER_BRIDGE_ELEMENTS = frozenset({"N", "O", "S"})

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

#: The three contact types as wire columns; fingerprint bit order is the same
#: sequence (ionic=0, hydrogen_bond=1, hydrophobic=2) so a matrix built from
#: bits and a table built from names can never disagree.
#: Contact types in wire order.  The first three indices are stable because
#: fingerprints and persisted results encode them; new types append.
CONTACT_TYPES: tuple[str, ...] = (
    "ionic",
    "hydrogen_bond",
    "hydrophobic",
    "halogen_bond",
    "metal_coordination",
    "water_mediated",
)
CONTACT_TYPE_ORDER: dict[str, int] = {name: i for i, name in enumerate(CONTACT_TYPES)}


# ── parsing (migrated from routers/interactions.py) ─────────────────────────


def parse_receptor_atoms(path: str) -> list[dict[str, Any]]:
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
                        if atom["element"] in INTERACTION_ELEMENTS or atom.get("metal"):
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


def parse_ligand_atoms(path: str = "", pdbqt_string: str = "") -> list[dict[str, Any]]:
    """Parse ligand atoms from SDF, PDBQT, or string."""
    atoms = []

    if pdbqt_string:
        atoms = parse_ligand_pdbqt(pdbqt_string)
    elif path:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if path.endswith(".pdbqt"):
                atoms = parse_ligand_pdbqt(content)
            elif path.endswith(".sdf"):
                atoms = parse_ligand_sdf(content)
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


def parse_ligand_pdbqt(content: str) -> list[dict[str, Any]]:
    """Parse atoms from PDBQT content, first model only.

    Docking output repeats the ligand once per MODEL; mixing them would
    multiply every contact.  A file with no MODEL record (single-model
    exports, hand-written fragments) parses whole — the filter only kicks in
    when models are actually declared.
    """
    lines = content.split("\n")
    model_start = next(
        (i for i, line in enumerate(lines) if line.startswith("MODEL")), None
    )
    if model_start is not None:
        end = next(
            (j for j in range(model_start + 1, len(lines)) if lines[j].startswith("ENDMDL")),
            len(lines),
        )
        lines = lines[model_start:end]

    atoms = []
    for line in lines:
        if line.startswith(("ATOM", "HETATM")):
            atom = _parse_pdb_atom(line, is_pdbqt=True)
            if atom:
                atoms.append(atom)
    return atoms


def parse_ligand_sdf(content: str) -> list[dict[str, Any]]:
    """Parse atoms from SDF content (first record of a multi-record file)."""
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
                        "charge": 0.0,
                        "metal": element in METAL_ELEMENTS,
                        "water": False,
                    })
            except (ValueError, IndexError):
                continue

    return atoms


def _parse_pdb_atom(line: str, *, is_pdbqt: bool) -> dict[str, Any] | None:
    """Parse a PDB or PDBQT ATOM/HETATM line.

    Columns 77-78 hold the element symbol in a PDB file and the AutoDock atom
    type in a PDBQT file, where a type may be two characters wide (``OA``,
    ``NA``, ``HD``, ``SA``).  Reading that column as a symbol gave aromatic
    carbons (type ``A``) the element ``A``, so every hydrophobic contact built
    on an aromatic ring was dropped from PDBQT input.

    Column 27 is the insertion code — blank in most files, but residues ``42``
    and ``42A`` share a sequence number, and a fingerprint that merges them
    would compare the wrong residues (task book勘误 ②).
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
        icode = line[26:27].strip()
        # The type/element field runs to the end of the record.
        column = line[76:].strip() if len(line) > 76 else ""

        if is_pdbqt:
            element = element_for(atom, column)
        else:
            element = column.capitalize() if column else element_for(atom, "")

        charge = 0.0
        if is_pdbqt and len(line) >= 76:
            try:
                charge = float(line[70:76].strip() or 0.0)
            except ValueError:
                charge = 0.0
        return {
            "x": x,
            "y": y,
            "z": z,
            "atom": atom,
            "residue": residue,
            "chain": chain,
            "resSeq": res_seq,
            "icode": icode,
            "element": element,
            "charged": (residue, atom) in CHARGED_SIDECHAIN_ATOMS,
            "charge": charge,
            "metal": element in METAL_ELEMENTS,
            "water": residue.upper() in WATER_RESIDUES,
        }
    except (ValueError, IndexError):
        return None


# ── classification + contacts ────────────────────────────────────────────────


def classify_contact(
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

    # Metal coordination: a retained metal ion and a ligand donor atom.  The
    # metal must be present in the receptor PDBQT; the preparation report says
    # whether it was kept.
    if (
        receptor.get("metal")
        and l_element in WATER_BRIDGE_ELEMENTS
        and distance <= METAL_COORDINATION_MAX_DISTANCE
    ):
        return "metal_coordination"

    # Halogen bond: a receptor polar atom and a ligand halogen.  This is a
    # distance-only candidate; the C-X...A angle is not available from PDBQT,
    # so the UI labels it as a candidate rather than a confirmed bond.
    if (
        r_element in WATER_BRIDGE_ELEMENTS
        and l_element in HALOGEN_ELEMENTS
        and distance < HALOGEN_BOND_MAX_DISTANCE
    ):
        return "halogen_bond"

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


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    dx = a["x"] - b["x"]
    dy = a["y"] - b["y"]
    dz = a["z"] - b["z"]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def find_contacts(
    receptor_atoms: list[dict[str, Any]],
    ligand_atoms: list[dict[str, Any]],
    distance_cutoff: float = DEFAULT_DISTANCE_CUTOFF,
) -> list[tuple[dict[str, Any], dict[str, Any], float, str]]:
    """Every (receptor atom, ligand atom, distance, type) contact within cutoff.

    Extracted from the analyze endpoint so the HTTP contact table and the
    fingerprint encoder can never drift apart (task book §4.1).  Distance
    stays the numpy ``float`` subclass it always was, so the wire's
    ``round(dist, 2)`` keeps serialising the way it always has.
    """
    import numpy as np

    contacts: list[tuple[dict[str, Any], dict[str, Any], float, str]] = []
    for r_atom in receptor_atoms:
        # Water is handled as a bridge below, never as a direct receptor atom.
        if r_atom.get("water"):
            continue
        for l_atom in ligand_atoms:
            dx = r_atom["x"] - l_atom["x"]
            dy = r_atom["y"] - l_atom["y"]
            dz = r_atom["z"] - l_atom["z"]
            dist = np.sqrt(dx * dx + dy * dy + dz * dz)

            if dist <= distance_cutoff:
                inter_type = classify_contact(r_atom, l_atom, dist)
                if inter_type:
                    contacts.append((r_atom, l_atom, dist, inter_type))

    # Water-mediated contacts: ligand donor/acceptor -> water -> receptor polar
    # atom.  The output row names the receptor bridge (not the water) and
    # carries the water coordinates in a nested ``water`` dict.
    waters = [
        atom for atom in receptor_atoms
        if atom.get("water") and atom.get("element") == "O"
    ]
    bridges = [
        atom for atom in receptor_atoms
        if not atom.get("water") and not atom.get("metal")
        and atom.get("element") in WATER_BRIDGE_ELEMENTS
    ]
    if waters and bridges:
        for water in waters:
            for ligand in ligand_atoms:
                if ligand.get("element") not in WATER_BRIDGE_ELEMENTS:
                    continue
                dlw = _distance(water, ligand)
                if dlw > min(WATER_MEDIATED_MAX_DISTANCE, distance_cutoff):
                    continue
                for bridge in bridges:
                    dbw = _distance(bridge, water)
                    if dbw > min(WATER_MEDIATED_MAX_DISTANCE, distance_cutoff):
                        continue
                    row = dict(bridge)
                    row["water"] = {
                        "residue": water.get("residue", ""),
                        "chain": water.get("chain", ""),
                        "resSeq": water.get("resSeq", ""),
                        "atom": water.get("atom", ""),
                        "x": water["x"],
                        "y": water["y"],
                        "z": water["z"],
                    }
                    row["waterDistance"] = round(float(dlw), 2)
                    row["bridgeDistance"] = round(float(dbw), 2)
                    contacts.append((row, ligand, dlw, "water_mediated"))
    return contacts


# ── fingerprint encoding ────────────────────────────────────────────────────


def residue_key(atom: dict[str, Any]) -> str:
    """Stable residue identity: ``A:ASP123`` (``A:GLU42B`` when an icode is set)."""
    return (
        f"{atom.get('chain', '')}:{atom.get('residue', '')}"
        f"{atom.get('resSeq', '')}{atom.get('icode', '')}"
    )


def residue_sort_key(atom: dict[str, Any]) -> tuple[str, int, str, str]:
    """``(chain, resSeq, icode)`` ordering (task book勘误 ②).

    Unparseable sequence numbers sort as 0 with the raw text as tiebreak, so
    the order stays deterministic whatever the file contains.
    """
    res_seq_text = atom.get("resSeq", "")
    try:
        res_seq = int(res_seq_text)
    except ValueError:
        res_seq = 0
    return (atom.get("chain", ""), res_seq, atom.get("icode", ""), res_seq_text)


def residue_columns(
    receptor_atoms: list[dict[str, Any]],
    bit_sets: list[frozenset[tuple[str, int]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Matrix columns: the residues any fingerprint touches, in sort order.

    Returns ``(rows, index_of)`` — wire-ready ``{key, resname, chain, resSeq,
    icode}`` rows and the residue-key → column-index map bit pairs are
    rewritten through.  Residues with no contact in any pose are dropped:
    an all-off column carries no information and only widens the matrix.
    """
    contact_keys = {key for bits in bit_sets for key, _type_order in bits}
    representatives: dict[str, dict[str, Any]] = {}
    for atom in receptor_atoms:
        key = residue_key(atom)
        if key in contact_keys and key not in representatives:
            representatives[key] = atom
    ordered_keys = sorted(
        representatives, key=lambda key: residue_sort_key(representatives[key])
    )
    index_of = {key: i for i, key in enumerate(ordered_keys)}
    rows = [
        {
            "key": key,
            "resname": representatives[key].get("residue", ""),
            "chain": representatives[key].get("chain", ""),
            "resSeq": _resseq_int(representatives[key]),
            "icode": representatives[key].get("icode", ""),
        }
        for key in ordered_keys
    ]
    return rows, index_of


def _resseq_int(atom: dict[str, Any]) -> int:
    """Sequence number as a number; unparseable text serialises as 0."""
    try:
        return int(atom.get("resSeq", ""))
    except ValueError:
        return 0


def fingerprint(
    receptor_atoms: list[dict[str, Any]],
    ligand_atoms: list[dict[str, Any]],
    distance_cutoff: float = DEFAULT_DISTANCE_CUTOFF,
) -> frozenset[tuple[str, int]]:
    """Contacts as ``(residue key, contact type order)`` bits.

    The search radius is the widest per-type threshold: a fingerprint bit can
    only say "this residue touches the ligand this way", so a narrower radius
    would silently drop types the caller never asked to drop.
    """
    bits: set[tuple[str, int]] = set()
    for r_atom, _l_atom, _dist, inter_type in find_contacts(
        receptor_atoms, ligand_atoms, distance_cutoff
    ):
        bits.add((residue_key(r_atom), CONTACT_TYPE_ORDER[inter_type]))
    return frozenset(bits)


def tanimoto(a: frozenset[tuple[str, int]], b: frozenset[tuple[str, int]]) -> float:
    """Tanimoto similarity of two bit sets; two empty sets are identical (1.0)."""
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 1.0


def butina_clustering(
    distances: list[list[float]], cutoff: float
) -> list[tuple[list[int], int]]:
    """BUTINA over a square distance matrix — same greedy semantics as
    ``core.chem.cluster`` (neighbours within cutoff, seed = most neighbours,
    pull in still-unassigned members) but self-contained on plain distances
    (task book §4.3 — cluster.py stays untouched).

    Returns ``(members, centroid)`` per cluster; the centroid is the member
    with the smallest mean distance to the others (ties → lowest index).
    """
    n = len(distances)
    if n == 0:
        return []
    neighbours = [
        [j for j in range(n) if j != i and distances[i][j] <= cutoff]
        for i in range(n)
    ]
    # Seed order: most neighbours first; stable sort keeps index order on ties.
    order = sorted(range(n), key=lambda i: -len(neighbours[i]))

    assigned = [False] * n
    clusters: list[tuple[list[int], int]] = []
    for seed in order:
        if assigned[seed]:
            continue
        members = [seed, *(j for j in neighbours[seed] if not assigned[j])]
        for index in members:
            assigned[index] = True
        clusters.append((members, _centroid_of(members, distances)))
    return clusters


def _centroid_of(members: list[int], distances: list[list[float]]) -> int:
    if len(members) == 1:
        return members[0]

    def mean_to_others(index: int) -> float:
        return sum(distances[index][other] for other in members if other != index) / (
            len(members) - 1
        )

    return min(members, key=mean_to_others)
