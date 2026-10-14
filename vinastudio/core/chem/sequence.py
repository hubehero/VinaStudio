"""Receptor sequence extraction for the sequence view (TASK-12).

The chain/residue walk mirrors ``pdb_lines.scan_residues`` semantics so the
sequence length reconciles with ``ReceptorInspection.residues``: every
``ATOM``/``HETATM`` group counts once, waters and ligands included (the view
renders them as disabled hetero cells rather than hiding them).  Only the
first model contributes — multi-MODEL NMR files would otherwise multiply the
same chain, and the viewer never shows model 2.

Secondary structure comes from records the file actually carries (PDB
``HELIX``/``SHEET``, mmCIF ``_struct_conf``/``_struct_sheet_range`` — gemmi
parses both into ``Structure.helices``/``sheets``).  This is annotation, not
prediction: a file without records yields residues with no ``ss`` and no
error, which the view draws as loop.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import gemmi

log = logging.getLogger(__name__)

#: Formats gemmi can walk for a polymer sequence; PDBQT has no residue names
#: in a form this view needs (the receptor panel shows the missing state).
_SEQUENCE_FORMATS: Final = frozenset({".pdb", ".ent", ".cif", ".mmcif"})


def extract_sequence(path: str | Path) -> dict | None:
    """Return ``{"chains": [{"id", "residues": [{seqId, name, het, ss?}]}]}``.

    ``None`` means "no sequence to show" (unsupported format, unreadable
    file, empty structure) — never an exception: the interface maps this to
    its "no sequence data" state.
    """
    file_path = Path(path)
    if file_path.suffix.lower() not in _SEQUENCE_FORMATS:
        return None

    try:
        structure = gemmi.read_structure(str(file_path))
    except Exception as exc:  # noqa: BLE001 - gemmi raises OSError/RuntimeError on bad input
        log.warning("sequence extraction failed for %s: %s", file_path, exc)
        return None

    if len(structure) == 0:
        return None

    marks = _secondary_structure(structure)
    chains: list[dict] = []
    for chain in structure[0]:
        residues: list[dict] = []
        for residue in chain:
            seq_id = residue.seqid.num
            icode = residue.seqid.icode
            entry: dict = {
                "seqId": seq_id,
                "name": residue.name,
                "het": residue.het_flag == "H",
            }
            ss = _ss_for(chain.name, seq_id, icode, marks)
            if ss is not None:
                entry["ss"] = ss
            residues.append(entry)
        if residues:
            chains.append({"id": chain.name, "residues": residues})

    if not chains:
        return None
    return {"chains": chains}


#: ``(chain, lo_seq, lo_icode, hi_seq, hi_icode, ss)`` — inclusive ranges.
_SSRange = tuple[str, int, str, int, str, str]


def _secondary_structure(structure: gemmi.Structure) -> list[_SSRange]:
    """Flatten helix/sheet records into per-chain inclusive ranges.

    Records that span two chains are dropped: neither the PDB format nor the
    view has a sensible way to render them, and every real file keeps a
    helix inside one chain.
    """
    ranges: list[_SSRange] = []
    for helix in structure.helices:
        start, end = helix.start, helix.end
        if start.chain_name != end.chain_name:
            continue
        ranges.append(
            _range_of(start.chain_name, start.res_id.seqid, end.res_id.seqid, "H")
        )
    for sheet in structure.sheets:
        for strand in sheet.strands:
            start, end = strand.start, strand.end
            if start.chain_name != end.chain_name:
                continue
            ranges.append(
                _range_of(start.chain_name, start.res_id.seqid, end.res_id.seqid, "E")
            )
    return ranges


def _range_of(
    chain: str, start: gemmi.SeqId, end: gemmi.SeqId, ss: str
) -> _SSRange:
    return (chain, start.num, start.icode, end.num, end.icode, ss)


def _ss_for(
    chain: str, seq_id: int, icode: str, marks: list[_SSRange]
) -> str | None:
    """Mark membership; insertion codes order after the space placeholder."""
    for lo_chain, lo_seq, lo_icode, hi_seq, hi_icode, ss in marks:
        if chain != lo_chain:
            continue
        after_lo = seq_id > lo_seq or (seq_id == lo_seq and icode >= lo_icode)
        before_hi = seq_id < hi_seq or (seq_id == hi_seq and icode <= hi_icode)
        if after_lo and before_hi:
            return ss
    return None
