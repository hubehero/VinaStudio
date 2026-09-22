"""Interaction classification must not depend on the input format.

The two defects this pins: carbon atoms were filtered out before the classifier
ran, so ``hydrophobic`` could never be returned at all; and aromatic carbons
(AutoDock type ``A``) were read as the element ``A``, so PDBQT input lost every
contact built on an aromatic ring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vinastudio.config import SAMPLE_DIR

SAMPLE_DIRECTORY = SAMPLE_DIR / "1iep"
RECEPTOR_PDBQT = SAMPLE_DIRECTORY / "1iep_receptor.pdbqt"
POSES_PDBQT = SAMPLE_DIRECTORY / "1iep_ligand_vina_out.pdbqt"


def _pdb_line(serial: int, name: str, resname: str, chain: str, resseq: int,
              x: float, y: float, z: float, element: str) -> str:
    """Format an ATOM record, elements in columns 77-78."""
    return (
        f"ATOM  {serial:>5} {name:<4} {resname:>3} {chain}{resseq:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {element:>2}"
    )


def _pdbqt_line(serial: int, name: str, resname: str, chain: str, resseq: int,
                x: float, y: float, z: float, atom_type: str) -> str:
    """Format an ATOM record the way the docking pipeline writes PDBQT."""
    return (
        f"ATOM  {serial:>5} {name:<4} {resname:>3} {chain}{resseq:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00    -0.300 {atom_type:<2}"
    )


#: Geometry chosen so each rule fires once: a charged side chain, a neutral
#: polar side chain, an aromatic ligand carbon, and one carbon beyond 4 A.
_RECEPTOR_ATOMS = [
    # (name, resname, resseq, x, y, z, element, pdbqt type)
    ("OD1", "ASP", 1, 0.0, 0.0, 0.0, "O", "OA"),
    ("OG", "SER", 2, 20.0, 0.0, 0.0, "O", "OA"),
    ("CD1", "LEU", 3, 10.0, 0.0, 0.0, "C", "C"),
    ("CE1", "LEU", 3, 10.0, 0.0, 7.5, "C", "C"),
]

_LIGAND_ATOMS = [
    # (name, x, y, z, pdbqt type)
    ("N1", 0.0, 0.0, 2.5, "N"),
    ("C1", 10.0, 0.0, 3.0, "A"),
    ("O1", 20.0, 0.0, 2.6, "OA"),
]


def _receptor_pdb(tmp_path: Path) -> Path:
    path = tmp_path / "receptor.pdb"
    lines = [
        _pdb_line(i, name, resname, "A", resseq, x, y, z, element)
        for i, (name, resname, resseq, x, y, z, element, _) in enumerate(_RECEPTOR_ATOMS, 1)
    ]
    path.write_text("\n".join(lines) + "\nEND\n", encoding="utf-8")
    return path


def _receptor_pdbqt(tmp_path: Path) -> Path:
    path = tmp_path / "receptor.pdbqt"
    lines = [
        _pdbqt_line(i, name, resname, "A", resseq, x, y, z, atom_type)
        for i, (name, resname, resseq, x, y, z, _, atom_type) in enumerate(_RECEPTOR_ATOMS, 1)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _ligand_pdbqt() -> str:
    lines = [
        _pdbqt_line(i, name, "UNL", " ", 1, x, y, z, atom_type)
        for i, (name, x, y, z, atom_type) in enumerate(_LIGAND_ATOMS, 1)
    ]
    return "\n".join(lines) + "\n"


#: AutoDock types to the element symbols an SDF file would carry.
_SDF_ELEMENTS = {"N": "N", "C": "C", "A": "C", "OA": "O", "NA": "N", "SA": "S", "HD": "H"}


def _ligand_sdf(tmp_path: Path) -> Path:
    """The same ligand written as SDF, where the element column is a symbol."""
    path = tmp_path / "ligand.sdf"
    lines = ["ligand", "  vinastudio", "", f"{len(_LIGAND_ATOMS):>3}  0  0  0  0  0  0  0  0  0999 V2000"]
    for _, x, y, z, atom_type in _LIGAND_ATOMS:
        # SDF carries elements, so an aromatic carbon is written as "C".
        element = _SDF_ELEMENTS[atom_type]
        lines.append(
            f"{x:>10.4f}{y:>10.4f}{z:>10.4f} {element:<3} 0  0  0  0  0  0  0  0  0  0  0  0"
        )
    lines.append("M  END")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _analyze(  # type: ignore[no-untyped-def]
    client,
    receptor: Path,
    *,
    ligand_pdbqt: str | None = None,
    ligand_path: Path | None = None,
) -> list[dict]:
    body: dict[str, object] = {"receptorPath": str(receptor), "distanceCutoff": 4.0}
    if ligand_pdbqt is not None:
        body["ligandPdbqtString"] = ligand_pdbqt
    if ligand_path is not None:
        body["ligandPath"] = str(ligand_path)

    response = client.post("/api/interactions/analyze", json=body)
    assert response.status_code == 200, response.text
    return response.json()["interactions"]


def _contacts(interactions: list[dict]) -> list[tuple[str, float]]:
    """What the two formats must agree on, ignoring how atoms are named."""
    return sorted((entry["type"], entry["distance"]) for entry in interactions)


def test_every_rule_fires_once(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    interactions = _analyze(client, _receptor_pdbqt(tmp_path), ligand_pdbqt=_ligand_pdbqt())

    by_type = {entry["type"]: entry for entry in interactions}
    assert set(by_type) == {"ionic", "hydrogen_bond", "hydrophobic"}

    # A charged side chain is a salt bridge, not a plain hydrogen bond.
    assert by_type["ionic"]["receptorResidue"] == "ASP"
    assert by_type["hydrogen_bond"]["receptorResidue"] == "SER"
    # The aromatic ligand carbon (type A) still counts as carbon.
    assert by_type["hydrophobic"]["ligandAtom"] == "C1"
    assert by_type["hydrophobic"]["receptorResidue"] == "LEU"

    # Every residue carries its chain and sequence number: bare resnames are
    # not identities (ILE, ILE, ILE... in a real pocket).
    assert by_type["ionic"]["receptorChain"] == "A"
    assert by_type["ionic"]["receptorResSeq"] == "1"
    assert by_type["hydrogen_bond"]["receptorResSeq"] == "2"
    assert by_type["hydrophobic"]["receptorResSeq"] == "3"

    # The aliphatic carbon 4.5 A away is outside the hydrophobic threshold.
    assert len(interactions) == 3


def test_pdb_and_pdbqt_receptors_agree(client, tmp_path: Path) -> None:
    ligand = _ligand_pdbqt()

    from_pdb = _analyze(client, _receptor_pdb(tmp_path), ligand_pdbqt=ligand)
    from_pdbqt = _analyze(client, _receptor_pdbqt(tmp_path), ligand_pdbqt=ligand)

    assert _contacts(from_pdb) == _contacts(from_pdbqt)


def test_sdf_and_pdbqt_ligands_agree(client, tmp_path: Path) -> None:
    receptor = _receptor_pdbqt(tmp_path)

    from_sdf = _analyze(client, receptor, ligand_path=_ligand_sdf(tmp_path))
    from_pdbqt = _analyze(client, receptor, ligand_pdbqt=_ligand_pdbqt())

    # An aromatic ligand carbon is typed "A" in PDBQT and written as "C" in SDF;
    # both must yield the same contacts.
    assert _contacts(from_sdf) == _contacts(from_pdbqt)


def test_the_receptor_is_required(client) -> None:  # type: ignore[no-untyped-def]
    """A ligand-only request used to pass validation and report zero contacts."""
    body = client.post("/api/interactions/analyze", json={
        "ligandPdbqtString": _ligand_pdbqt(),
        "distanceCutoff": 4.0,
    })
    assert body.status_code == 422
    assert "receptorPath is required" in body.json()["detail"]


def test_an_unreadable_receptor_is_an_error_not_an_empty_table(
    client, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    body = client.post("/api/interactions/analyze", json={
        "receptorPath": str(tmp_path / "missing.pdb"),
        "ligandPdbqtString": _ligand_pdbqt(),
        "distanceCutoff": 4.0,
    })
    assert body.status_code == 422
    assert "cannot read receptor file" in body.json()["detail"]


def test_a_receptor_without_atom_records_is_rejected(
    client, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    empty = tmp_path / "empty.pdb"
    empty.write_text("REMARK nothing here\nEND\n", encoding="utf-8")

    body = client.post("/api/interactions/analyze", json={
        "receptorPath": str(empty),
        "ligandPdbqtString": _ligand_pdbqt(),
        "distanceCutoff": 4.0,
    })
    assert body.status_code == 422
    assert "no ATOM/HETATM" in body.json()["detail"]


def test_an_unreadable_ligand_is_an_error_not_an_empty_table(
    client, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    body = client.post("/api/interactions/analyze", json={
        "receptorPath": str(_receptor_pdbqt(tmp_path)),
        "ligandPath": str(tmp_path / "missing.sdf"),
        "distanceCutoff": 4.0,
    })
    assert body.status_code == 422
    assert "cannot read ligand file" in body.json()["detail"]


def _first_model(text: str) -> str:
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("MODEL"):
            inside = True
            continue
        if line.startswith("ENDMDL"):
            break
        if inside:
            lines.append(line)
    return "\n".join(lines)


@pytest.mark.skipif(
    not (RECEPTOR_PDBQT.exists() and POSES_PDBQT.exists()),
    reason="the 1iep reference data is not present in vinastudio/resources/sample",
)
def test_reference_complex_reports_hydrophobic_contacts(client) -> None:  # type: ignore[no-untyped-def]
    interactions = _analyze(
        client,
        RECEPTOR_PDBQT,
        ligand_pdbqt=_first_model(POSES_PDBQT.read_text("utf-8")),
    )

    assert interactions, "no contacts at all against the 1iep reference complex"
    kinds = {entry["type"] for entry in interactions}
    assert "hydrogen_bond" in kinds
    # 236 aromatic and 1199 aliphatic receptor carbons face an aromatic ligand.
    assert "hydrophobic" in kinds
