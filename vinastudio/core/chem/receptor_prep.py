"""Receptor preparation: PDB/mmCIF -> PDBQT through Meeko's ``Polymer``.

Meeko matches the input against per-residue chemical templates, which is what
makes the result trustworthy: connectivity, bond orders, protonation state and
formal charges come from the templates, so a structure that survives matching is
chemically correct rather than merely coordinate-complete.

Two real-world problems have to be handled before the templates get a chance:

**Residues split across the file.** Meeko's parser assumes the atoms of a
residue are contiguous. The upstream 1iep reference file, for example, has a
single ``HB2`` atom of ``SER A 438`` on its second line and the rest of that
residue near the end. That is legal PDB, and it makes Meeko reject the whole
structure with "interrupted residues". :func:`normalise_pdb_atom_order` groups
each residue with its own largest block of atoms, which is a chemical no-op and
preserves the original residue order.

**Waters, ions and co-crystallised ligands.** These are usually stripped before
docking, and which ones to strip is the user's decision, so they are enumerated
and reported rather than silently dropped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from vinastudio.core.chem.formats import detect_format, is_supported, normalise_suffix
from vinastudio.core.chem.mmcif import mmcif_to_pdb, scan_mmcif_residues
from vinastudio.core.chem.pdb_lines import (
    group_runs,
    residue_key,
    scan_residues,
    split_solvent,
)
from vinastudio.core.errors import (
    InvalidInputError,
    PreparationError,
    ReceptorTemplateError,
    UnsupportedFormatError,
    brief_error,
)

log = logging.getLogger(__name__)

#: Residue identifiers look like ``A:438`` or ``A:42B`` (with an insertion code).
_RESIDUE_TOKEN_RE = re.compile(r"['\"]([A-Za-z0-9]{0,2}:\d*\w*)['\"]")


@dataclass(frozen=True, slots=True)
class ReceptorPrepOptions:
    """User-facing choices for receptor preparation."""

    delete_waters: bool = True
    delete_hetero: bool = True
    """Strip non-water ``HETATM`` groups (ions, cofactors, co-crystallised ligands)."""
    flexible_residues: tuple[str, ...] = ()
    """Residues to make flexible, as ``chain:resnum`` keys such as ``('A:42',)``."""
    allow_bad_residues: bool = False
    normalise_atom_order: bool = True
    """Group each residue's atoms together; see the module docstring."""


@dataclass(slots=True)
class ReceptorReport:
    """What actually happened, in a shape the interface can display."""

    source: str
    input_format: str
    input_atoms: int
    input_residues: int
    deleted_waters: list[str] = field(default_factory=list)
    deleted_hetero: list[str] = field(default_factory=list)
    normalised_atom_order: bool = False
    valid_residues: int = 0
    ignored_residues: list[str] = field(default_factory=list)
    flexible_residues: list[str] = field(default_factory=list)
    output_atoms: int = 0
    atom_types: dict[str, int] = field(default_factory=dict)
    include_hydrogens: bool = True
    warnings: list[str] = field(default_factory=list)
    residue_list: list[str] = field(default_factory=list)
    """All valid residue identifiers (e.g. ``A:42``) for the flexible selector."""


@dataclass(slots=True)
class ReceptorPreparation:
    """Result of a successful preparation."""

    pdbqt: str
    """Rigid receptor PDBQT, for ``Vina.set_receptor``."""
    flex_pdbqt: str | None
    """Flexible-sidechain PDBQT, when any residue was made flexible."""
    pdb: str
    """Processed receptor as PDB, for the 3D view (PDBQT is not renderable)."""
    report: ReceptorReport


@dataclass(slots=True)
class ReceptorInspection:
    """Cheap pre-flight view of a receptor file."""

    source: str
    input_format: str
    preparable: bool
    atoms: int
    residues: int
    chains: int
    waters: list[str]
    hetero: list[str]
    residue_names: list[str]
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# PDB scanning helpers
# --------------------------------------------------------------------------


def normalise_pdb_atom_order(text: str) -> tuple[str, bool]:
    """Group the atoms of each residue together, keeping the residue order.

    Only atom records are moved, and only among the line positions atom records
    already occupy, so headers, ``TER`` and ``END`` stay exactly where they were.
    Each residue is anchored at its largest contiguous block, which leaves clean
    files untouched and puts a stray atom back with its own residue.
    """
    lines = text.splitlines()
    indices = [index for index, line in enumerate(lines) if line.startswith(("ATOM", "HETATM"))]
    if len(indices) < 2:
        return text, False

    keys = [residue_key(lines[index]) for index in indices]

    # Anchor each residue at its largest contiguous run, so a stray atom that
    # appears early in the file does not drag its whole residue there.
    runs: dict[str, list[tuple[int, int]]] = {}
    for key, start, end in group_runs(keys):
        runs.setdefault(key, []).append((start, end))
    anchor = {key: max(spans, key=lambda span: span[1] - span[0])[0] for key, spans in runs.items()}

    order = sorted(range(len(keys)), key=lambda position: (anchor[keys[position]], position))
    if order == list(range(len(keys))):
        return text, False

    reordered = list(lines)
    for slot, source in zip(indices, order, strict=True):
        reordered[slot] = lines[indices[source]]
    return "\n".join(reordered) + "\n", True


def _extract_residues(message: str) -> tuple[str, ...]:
    """Pull residue identifiers out of a Meeko error message."""
    return tuple(dict.fromkeys(_RESIDUE_TOKEN_RE.findall(message)))


# --------------------------------------------------------------------------
# inspection
# --------------------------------------------------------------------------


def inspect_receptor(path: str | Path) -> ReceptorInspection:
    """Describe a receptor file without parameterising it."""
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")
    if not is_supported(file_path, "receptor"):
        raise UnsupportedFormatError(
            f"unsupported receptor extension {file_path.suffix!r}; "
            "expected one of .pdb .ent .cif .mmcif .pdbqt"
        )

    fmt = detect_format(file_path) or file_path.suffix.lstrip(".")
    text = file_path.read_text(encoding="utf-8", errors="replace")

    if fmt == "pdbqt":
        from vinastudio.core.chem.pdbqt import parse_pdbqt

        document = parse_pdbqt(text, source=str(file_path))
        pose = document.first_pose
        residues = {f"{a.chain}:{a.resid}" for a in pose.atoms}
        return ReceptorInspection(
            source=str(file_path),
            input_format=fmt,
            preparable=False,
            atoms=pose.n_atoms,
            residues=len(residues),
            chains=len({a.chain for a in pose.atoms}),
            waters=[],
            hetero=[],
            residue_names=sorted({a.resname for a in pose.atoms}),
            notes=["already PDBQT; it is used as the rigid receptor directly"],
        )

    # mmCIF: convert to PDB for inspection
    if fmt in ("cif", "mmcif"):
        mmcif_residues = scan_mmcif_residues(text)
        waters = [k for k, v in mmcif_residues.items() if v.is_water]
        hetero = [k for k, v in mmcif_residues.items() if v.is_hetero and not v.is_water]

        notes: list[str] = []
        if waters:
            notes.append(f"{len(waters)} water molecules present")
        if hetero:
            notes.append(f"{len(hetero)} non-water HETATM groups present")

        return ReceptorInspection(
            source=str(file_path),
            input_format=fmt,
            preparable=True,
            atoms=sum(v.atoms for v in mmcif_residues.values()),
            residues=len(mmcif_residues),
            chains=len({k.split(":")[0] for k in mmcif_residues}),
            waters=sorted(waters),
            hetero=sorted(hetero),
            residue_names=sorted({v.name for v in mmcif_residues.values()}),
            notes=notes,
        )

    # PDB format
    residues = scan_residues(text)
    waters, hetero = split_solvent(residues)
    chains = {line[21:22] for line in text.splitlines() if line.startswith("ATOM")}
    names = sorted({entry.name for entry in residues.values()})

    notes: list[str] = []
    if waters:
        notes.append(f"{len(waters)} water molecules present")
    if hetero:
        notes.append(f"{len(hetero)} non-water HETATM groups present")

    # A small-molecule PDB (single chain, few residues) is technically valid
    # as a receptor but almost certainly not what the user intended.
    n_residues = len(residues)
    n_chains = len(chains)
    if n_residues <= 5 and n_chains <= 1:
        notes.append(
            f"only {n_residues} residue(s) in {n_chains} chain(s) -- "
            "this looks like a small molecule, not a protein receptor; "
            "for docking ligands against a protein, use the receptor panel "
            "with a multi-chain PDB instead"
        )

    return ReceptorInspection(
        source=str(file_path),
        input_format=fmt,
        preparable=True,
        atoms=sum(entry.atoms for entry in residues.values()),
        residues=len(residues),
        chains=len(chains),
        waters=sorted(waters),
        hetero=sorted(hetero),
        residue_names=names,
        notes=notes,
    )


# --------------------------------------------------------------------------
# preparation
# --------------------------------------------------------------------------


def prepare_receptor(
    path: str | Path,
    options: ReceptorPrepOptions | None = None,
) -> ReceptorPreparation:
    """Parameterise a receptor into PDBQT.

    Raises :class:`ReceptorTemplateError` when Meeko's templates reject residues
    (carrying their identifiers so the interface can offer to exclude them),
    :class:`InvalidInputError` for unreadable input, and
    :class:`UnsupportedFormatError` for the wrong extension.
    """
    from meeko import MoleculePreparation, PDBQTWriterLegacy, Polymer

    options = options or ReceptorPrepOptions()
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")
    if not is_supported(file_path, "receptor"):
        raise UnsupportedFormatError(
            f"unsupported receptor extension {file_path.suffix!r}; "
            "expected one of .pdb .ent .cif .mmcif .pdbqt"
        )
    if normalise_suffix(file_path) == ".pdbqt":
        raise UnsupportedFormatError(
            f"{file_path.name} is already PDBQT; it does not need parameterisation"
        )

    original = file_path.read_text(encoding="utf-8", errors="replace")

    # Convert mmCIF to PDB if needed
    fmt = detect_format(file_path) or file_path.suffix.lstrip(".")
    if fmt in ("cif", "mmcif"):
        try:
            original = mmcif_to_pdb(original)
        except Exception as exc:
            raise PreparationError(
                f"failed to convert mmCIF to PDB: {brief_error(exc)}"
            ) from exc
        # Re-scan residues from the converted PDB
        residues = scan_residues(original)
    else:
        residues = scan_residues(original)
    waters, hetero = split_solvent(residues)

    warnings: list[str] = []
    text = original
    normalised = False
    if options.normalise_atom_order:
        text, normalised = normalise_pdb_atom_order(text)

    to_delete: list[str] = []
    if options.delete_waters:
        to_delete.extend(waters)
    if options.delete_hetero:
        to_delete.extend(hetero)

    try:
        polymer = Polymer.from_pdb_string(
            text,
            residues_to_delete=to_delete or None,
            allow_bad_res=options.allow_bad_residues,
        )
    except ValueError as exc:
        message = str(exc)
        offenders = _extract_residues(message)
        if "interrupted residues" in message:
            raise ReceptorTemplateError(
                f"{file_path.name} has residues whose atoms are not contiguous, and "
                f"reordering did not resolve it: {', '.join(offenders)}",
                offenders,
            ) from exc
        raise ReceptorTemplateError(
            f"Meeko rejected {file_path.name}: {brief_error(message)}", offenders
        ) from exc
    except Exception as exc:
        raise PreparationError(
            f"could not read {file_path.name}: {brief_error(exc)}"
        ) from exc

    valid = polymer.get_valid_monomers()
    ignored = sorted(set(polymer.get_ignored_monomers()))

    # All residue identifiers available for flexible-sidechain selection.
    residue_list = sorted(valid)

    mk_prep = MoleculePreparation()
    for residue_id in options.flexible_residues:
        if residue_id not in valid:
            warnings.append(f"flexible residue {residue_id} is not in the structure; ignored")
            continue
        polymer.flexibilize_sidechain(residue_id, mk_prep)

    try:
        polymer.parameterize(mk_prep)
    except Exception as exc:
        raise PreparationError(
            f"parameterisation failed for {file_path.name}: {brief_error(exc)}"
        ) from exc

    try:
        rigid_pdbqt, flex_dict = PDBQTWriterLegacy.write_from_polymer(polymer)
    except Exception as exc:
        raise PreparationError(
            f"PDBQT writer rejected {file_path.name}: {brief_error(exc)}"
        ) from exc

    if not rigid_pdbqt.strip():
        raise PreparationError(
            f"no rigid receptor was produced from {file_path.name}; "
            "every residue was either deleted or rejected"
        )

    from vinastudio.core.chem.pdbqt import parse_pdbqt

    parsed = parse_pdbqt(rigid_pdbqt)
    pose = parsed.first_pose
    if not pose.atoms:
        raise PreparationError(f"{file_path.name} produced an empty receptor PDBQT")

    if ignored:
        warnings.append(
            f"{len(ignored)} residues were not matched by Meeko's templates and were "
            "excluded from the receptor"
        )
    if not any(atom.is_polar_hydrogen for atom in pose.atoms):
        warnings.append(
            "the receptor has no polar hydrogens; docking scores depend on them, "
            "so supply a protonated structure"
        )

    flex_pdbqt = "".join(flex_dict.values()) if flex_dict else None

    return ReceptorPreparation(
        pdbqt=rigid_pdbqt,
        flex_pdbqt=flex_pdbqt,
        pdb=polymer.to_pdb(),
        report=ReceptorReport(
            source=str(file_path),
            input_format=detect_format(file_path) or file_path.suffix.lstrip("."),
            input_atoms=sum(entry.atoms for entry in residues.values()),
            input_residues=len(residues),
            deleted_waters=sorted(waters) if options.delete_waters else [],
            deleted_hetero=sorted(hetero) if options.delete_hetero else [],
            normalised_atom_order=normalised,
            valid_residues=len(valid),
            ignored_residues=ignored,
            flexible_residues=list(options.flexible_residues),
            output_atoms=pose.n_atoms,
            atom_types=dict(pose.atom_types),
            include_hydrogens=any(atom.is_polar_hydrogen for atom in pose.atoms),
            warnings=warnings,
            residue_list=residue_list,
        ),
    )
