"""AutoDock atom types and the element each one stands for.

AutoDock types live in their own namespace and *collide* with element symbols:
``NA`` is an acceptor nitrogen rather than sodium, and ``A`` is aromatic carbon.
A PDBQT record puts a type where a PDB record puts an element, so every module
that reads both formats has to resolve them the same way. The rule lives here
rather than in one of its callers so it cannot drift, and so ``pdbqt`` does not
have to import ``export`` (which imports ``pdbqt``).
"""

from __future__ import annotations

from typing import Final

#: AutoDock atom type to chemical element.
AUTODOCK_TYPE_TO_ELEMENT: Final[dict[str, str]] = {
    "H": "H",
    "HD": "H",
    "HS": "H",
    "C": "C",
    "A": "C",
    "N": "N",
    "NA": "N",
    "O": "O",
    "OA": "O",
    "S": "S",
    "SA": "S",
    "P": "P",
    "F": "F",
    "CL": "Cl",
    "BR": "Br",
    "I": "I",
    "SI": "Si",
    "B": "B",
    "MG": "Mg",
    "MN": "Mn",
    "ZN": "Zn",
    "CA": "Ca",
    "FE": "Fe",
}


def element_for(name: str, atom_type: str = "") -> str:
    """Element symbol for an atom record.

    The AutoDock type is authoritative when it is one this project knows; only
    an unknown type falls back to reading the atom name.
    """
    if atom_type:
        mapped = AUTODOCK_TYPE_TO_ELEMENT.get(atom_type.upper())
        if mapped is not None:
            return mapped

    stripped = name.strip()
    if not stripped:
        return ""
    pair = stripped[:2]
    if len(pair) == 2 and pair[0].isalpha() and pair[1].islower():
        return pair.capitalize()
    return stripped[0].upper()
