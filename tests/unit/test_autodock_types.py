"""The AutoDock type decides the element, not the spelling of a name.

Types and element symbols collide (``NA`` is an acceptor nitrogen, not sodium;
``A`` is aromatic carbon), and a PDBQT record puts a type where a PDB record
puts an element. Two code paths used to resolve this differently, so the same
atom had different elements depending on which module looked at it.
"""

from __future__ import annotations

import pytest

from vinastudio.core.chem.autodock_types import element_for
from vinastudio.core.chem.pdbqt import parse_pdbqt

COLUMNS = "  1.00  0.00    -0.300 "


def _atom_line(serial: int, name: str, atom_type: str) -> str:
    return (
        f"ATOM  {serial:>5} {name:<4} LIG A   1    "
        f"{0.0:>8.3f}{0.0:>8.3f}{0.0:>8.3f}{COLUMNS}{atom_type:<2}"
    )


@pytest.mark.parametrize(
    ("name", "atom_type", "expected"),
    [
        ("C1", "A", "C"),  # aromatic carbon
        ("C1", "C", "C"),
        ("N1", "NA", "N"),  # acceptor nitrogen, not sodium
        ("O1", "OA", "O"),  # acceptor oxygen
        ("H1", "HD", "H"),
        ("S1", "SA", "S"),  # acceptor sulfur, not an aromatic-carbon pair
        ("CL1", "CL", "Cl"),
    ],
)
def test_element_follows_the_autodock_type(name: str, atom_type: str, expected: str) -> None:
    assert element_for(name, atom_type) == expected


def test_element_falls_back_to_the_name_for_unknown_types() -> None:
    assert element_for("C1", "") == "C"
    assert element_for("Cl1", "") == "Cl"
    assert element_for("", "") == ""


def test_parsed_pdbqt_atoms_report_real_elements() -> None:
    content = "\n".join([
        _atom_line(1, "N1", "NA"),
        _atom_line(2, "O1", "OA"),
        _atom_line(3, "C1", "A"),
        _atom_line(4, "H1", "HD"),
    ]) + "\n"

    atoms = parse_pdbqt(content).first_pose.atoms

    assert [atom.element for atom in atoms] == ["N", "O", "C", "H"]
