"""Pure-RDKit chemistry behind the 2D sketch editor (TASK-25).

The editor owns pixels; this module owns chemistry.  Every function here is a
computation over plain dataclasses — no Qt, no FastAPI, no filesystem — so the
same code answers ``/api/chem/sketch/analyze`` and ``/api/chem/sketch/cleanup``
and the unit tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rdkit import Chem
from rdkit.Chem import AllChem

from vinastudio.core.errors import InvalidInputError, brief_error

log = logging.getLogger(__name__)

#: Scene pixels per bond at zoom 1: 75 px = 1.5 A (a C-C bond), so the editor
#: and this module convert with the same constant — cleanup coordinates in
#: Angstrom must land back where the drawing expects them.
ANGSTROM_PER_PX = 0.02

#: Mean bond length cleanup normalises to: the same 1.5 A the drawing treats
#: as canonical (75 px × ANGSTROM_PER_PX).
TARGET_BOND_ANGSTROM = 1.5

#: Key order the drawing tools can produce.  1.5 is accepted for robustness
#: (aromatic input) but has no tool behind it in stage A.
_BOND_ORDERS: dict[float, Chem.BondType] = {
    1.0: Chem.BondType.SINGLE,
    1.5: Chem.BondType.AROMATIC,
    2.0: Chem.BondType.DOUBLE,
    3.0: Chem.BondType.TRIPLE,
}

#: stereo 1 = wedge, 2 = hash; both live on the begin (a1) side, matching
#: how the canvas draws the narrow end of a wedge.
_STEREO_DIRS: dict[int, Chem.BondDir] = {
    1: Chem.BondDir.BEGINWEDGE,
    2: Chem.BondDir.BEGINDASH,
}

#: The editor's atom id travels on the RDKit atom so every answer (implicit
#: H counts, problem atoms, ring membership) can come back keyed the way the
#: canvas sent it.
_ID_PROP = "_original_atom_id"

#: RDKit reports valence/kekulize failures in English; the UI shows these to
#: the user, so the two common cases get Chinese summaries and the raw text
#: stays as a fallback.
_PROBLEM_TEXT: dict[str, str] = {
    "AtomValenceException": "原子的价键数超出允许范围",
    "KekulizeException": "环无法写出合法的交替键级",
}


@dataclass(frozen=True)
class SketchAtom:
    """One drawn atom.  Coordinates are scene pixels (y grows downward)."""

    id: int
    symbol: str
    x: float
    y: float
    charge: int = 0
    radical: int = 0


@dataclass(frozen=True)
class SketchBond:
    """One drawn bond.  ``stereo``: 0 none, 1 wedge, 2 hash — drawn at a1."""

    a1: int
    a2: int
    order: float = 1.0
    stereo: int = 0


@dataclass(frozen=True)
class SketchRing:
    """A ring perceived after sanitisation.

    ``center`` is the geometric mean of the *input* pixel positions (not the
    Angstrom conformer): the canvas draws ring-interior double-bond offsets in
    scene pixels, and re-deriving the centre client-side would duplicate the
    ring perception RDKit just did.
    """

    atom_ids: tuple[int, ...]
    center: tuple[float, float]


@dataclass
class SketchAnalysis:
    """The analyze answer; ``smiles`` is None whenever chemistry failed."""

    smiles: str | None
    implicit_h: dict[int, int] = field(default_factory=dict)
    problems: list[int] = field(default_factory=list)
    rings: list[SketchRing] = field(default_factory=list)
    error: str | None = None


def build_mol(
    atoms: list[SketchAtom], bonds: list[SketchBond]
) -> tuple[Chem.RWMol, dict[int, int]]:
    """Assemble the drawing into an RWMol with a 2D conformer — no sanitisation.

    Structural nonsense (empty canvas, unknown symbol, dangling bond, duplicate
    bond) is a *bad request*, not a chemical verdict, so it raises
    InvalidInputError (422) instead of coming back as a null analysis.
    """
    if not atoms:
        raise InvalidInputError("画布是空的：请先放置原子再分析")
    table = Chem.GetPeriodicTable()
    mol = Chem.RWMol()
    index_of: dict[int, int] = {}
    for atom in atoms:
        if atom.id in index_of:
            raise InvalidInputError(f"原子 id 重复：{atom.id}")
        raw = atom.symbol.strip()
        canonical = raw[:1].upper() + raw[1:].lower() if raw else raw
        try:
            atomic_number = table.GetAtomicNumber(canonical)
        except RuntimeError:
            raise InvalidInputError(f"未知元素符号：{atom.symbol}") from None
        rd_atom = Chem.Atom(atomic_number)
        rd_atom.SetFormalCharge(atom.charge)
        if atom.radical:
            rd_atom.SetNumRadicalElectrons(atom.radical)
        rd_atom.SetProp(_ID_PROP, str(atom.id))
        index_of[atom.id] = mol.AddAtom(rd_atom)

    seen_pairs: set[frozenset[int]] = set()
    for bond in bonds:
        if bond.a1 == bond.a2:
            raise InvalidInputError(f"键的两端是同一个原子：{bond.a1}")
        if bond.a1 not in index_of or bond.a2 not in index_of:
            missing = bond.a1 if bond.a1 not in index_of else bond.a2
            raise InvalidInputError(f"键引用了不存在的原子：{missing}")
        if bond.order not in _BOND_ORDERS:
            raise InvalidInputError(f"不支持的键级：{bond.order}")
        if bond.stereo not in _STEREO_DIRS and bond.stereo != 0:
            raise InvalidInputError(f"不支持的键方向标记：{bond.stereo}")
        pair = frozenset((bond.a1, bond.a2))
        if pair in seen_pairs:
            raise InvalidInputError(f"原子 {bond.a1} 与 {bond.a2} 之间已经有键了")
        seen_pairs.add(pair)
        mol.AddBond(index_of[bond.a1], index_of[bond.a2], _BOND_ORDERS[float(bond.order)])
        if bond.stereo:
            mol.GetBondBetweenAtoms(index_of[bond.a1], index_of[bond.a2]).SetBondDir(
                _STEREO_DIRS[bond.stereo]
            )

    conf = Chem.Conformer(mol.GetNumAtoms())
    conf.Set3D(False)
    for atom in atoms:
        # The Python wrapper insists on a 3-tuple even for a 2D conformer;
        # y is negated because the canvas grows downward and chemistry does not.
        conf.SetAtomPosition(
            index_of[atom.id],
            (atom.x * ANGSTROM_PER_PX, -atom.y * ANGSTROM_PER_PX, 0.0),
        )
    mol.AddConformer(conf, assignId=True)
    return mol, index_of


def analyze(atoms: list[SketchAtom], bonds: list[SketchBond]) -> SketchAnalysis:
    """Chemical feedback for the canvas: SMILES, implicit H, problems, rings.

    Invalid chemistry never raises — the drawing is mid-edit by definition, so
    a bad valence comes back as ``smiles=None`` plus a human explanation and
    the offending atom ids for the red frames.
    """
    mol, _ = build_mol(atoms, bonds)

    problems = Chem.DetectChemistryProblems(mol)
    if problems:
        atom_ids: list[int] = []
        parts: list[str] = []
        for problem in problems:
            text = _PROBLEM_TEXT.get(problem.GetType(), problem.Message())
            get_idx = getattr(problem, "GetAtomIdx", None)
            if callable(get_idx):
                original = int(mol.GetAtomWithIdx(get_idx()).GetProp(_ID_PROP))
                if original not in atom_ids:
                    atom_ids.append(original)
                parts.append(f"{text}（原子 {original}）")
            else:
                parts.append(text)
        # dict.fromkeys: dedupe in order — RDKit can report the same class of
        # problem once per atom and the user only needs to hear it once.
        error = "结构无法成立：" + "；".join(dict.fromkeys(parts))
        return SketchAnalysis(smiles=None, problems=atom_ids, error=error)

    try:
        Chem.SanitizeMol(mol)
        # Wedge/hash bonds only become chiral tags once someone reads them;
        # this is the step that makes "@@" appear in the SMILES.
        Chem.AssignChiralTypesFromBondDirs(mol, confId=0, replaceExistingTags=True)
        Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
        smiles = Chem.MolToSmiles(mol, isomericSmiles=True)
    except Exception as exc:  # RDKit failing here is a user-facing verdict, not a crash
        log.debug("sketch sanitize failed", exc_info=True)
        return SketchAnalysis(smiles=None, error=f"结构未通过化学检查：{brief_error(exc)}")

    # GetTotalNumHs, not GetNumImplicitHs: aromatic N-H (pyrrole, amides)
    # reports zero implicit H on some paths but never zero total.
    implicit_h: dict[int, int] = {}
    for rd_atom in mol.GetAtoms():
        count = rd_atom.GetTotalNumHs()
        if count:
            implicit_h[int(rd_atom.GetProp(_ID_PROP))] = count

    pixel_positions = {atom.id: (atom.x, atom.y) for atom in atoms}
    rings: list[SketchRing] = []
    for ring in mol.GetRingInfo().AtomRings():
        ids = tuple(int(mol.GetAtomWithIdx(i).GetProp(_ID_PROP)) for i in ring)
        centre = (
            sum(pixel_positions[i][0] for i in ids) / len(ids),
            sum(pixel_positions[i][1] for i in ids) / len(ids),
        )
        rings.append(SketchRing(atom_ids=ids, center=centre))

    return SketchAnalysis(smiles=smiles, implicit_h=implicit_h, rings=rings)


@dataclass(frozen=True)
class LayoutAtom:
    """One atom from a SMILES layout.

    ``x``/``y`` are Angstrom on the **chemical frame** (y grows upward) — the
    ``cleanup_coords`` convention, so the client converts both the same way.
    """

    id: int
    symbol: str
    x: float
    y: float
    charge: int = 0
    radical: int = 0


@dataclass(frozen=True)
class LayoutBond:
    """Kekule order 1/2/3; stereo 0 none, 1 wedge, 2 hash — drawn at a1."""

    a1: int
    a2: int
    order: int = 1
    stereo: int = 0


@dataclass
class SketchLayout:
    """The whole drawing a SMILES import replaces the canvas with."""

    atoms: list[LayoutAtom] = field(default_factory=list)
    bonds: list[LayoutBond] = field(default_factory=list)


def _scale_bond_lengths(mol: Chem.Mol) -> None:
    """Scale the conformer about its centroid to the canonical 1.5 A bond.

    Shared by cleanup and layout so an imported molecule occupies the same
    pixel budget as a tidied-up drawing; in place, because both callers just
    rebuilt the conformer moments ago.
    """
    conf = mol.GetConformer()
    lengths = [
        conf.GetAtomPosition(bond.GetBeginAtomIdx()).Distance(
            conf.GetAtomPosition(bond.GetEndAtomIdx())
        )
        for bond in mol.GetBonds()
    ]
    if not lengths:
        return
    mean = sum(lengths) / len(lengths)
    if mean <= 1e-9:
        return
    scale = TARGET_BOND_ANGSTROM / mean
    count = mol.GetNumAtoms()
    centre_x = sum(conf.GetAtomPosition(i).x for i in range(count)) / count
    centre_y = sum(conf.GetAtomPosition(i).y for i in range(count)) / count
    for i in range(count):
        point = conf.GetAtomPosition(i)
        conf.SetAtomPosition(
            i,
            (
                centre_x + (point.x - centre_x) * scale,
                centre_y + (point.y - centre_y) * scale,
                0.0,
            ),
        )


def layout_smiles(smiles: str) -> SketchLayout:
    """SMILES → 2D drawing data for the canvas import (TASK-26 C5).

    Kekulize before reading orders: the canvas only understands 1/2/3.
    ``WedgeMolBonds`` re-derives wedge/hash from the SMILES chirality, which
    is what lets ``C[C@H]...`` come back into the editor as a marked centre.
    Coordinates stay in the cleanup frame — same conversion on the client.
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
    except Exception as exc:  # exotic parse crashes are still a 422, not a 500
        log.debug("sketch layout parse failed", exc_info=True)
        raise InvalidInputError(f"无法解析 SMILES：{brief_error(exc)}") from None
    if mol is None:
        raise InvalidInputError("无法解析 SMILES：请检查括号、环号与原子符号")
    try:
        AllChem.Compute2DCoords(mol, canonOrient=True)
        Chem.Kekulize(mol, clearAromaticFlags=True)
        Chem.WedgeMolBonds(mol, mol.GetConformer())
    except Exception as exc:
        log.debug("sketch layout failed", exc_info=True)
        raise InvalidInputError(f"无法生成该分子的二维布局：{brief_error(exc)}") from None
    _scale_bond_lengths(mol)

    conf = mol.GetConformer()
    atoms = [
        LayoutAtom(
            id=atom.GetIdx() + 1,
            symbol=atom.GetSymbol(),
            x=conf.GetAtomPosition(atom.GetIdx()).x,
            y=conf.GetAtomPosition(atom.GetIdx()).y,
            charge=atom.GetFormalCharge(),
            radical=atom.GetNumRadicalElectrons(),
        )
        for atom in mol.GetAtoms()
    ]
    bonds: list[LayoutBond] = []
    for bond in mol.GetBonds():
        stereo = 0
        # Wedge/hash only ever mark single bonds (drawn contract, stereo is
        # meaningless on a double/triple bond).
        if bond.GetBondType() == Chem.BondType.SINGLE:
            if bond.GetBondDir() == Chem.BondDir.BEGINWEDGE:
                stereo = 1
            elif bond.GetBondDir() == Chem.BondDir.BEGINDASH:
                stereo = 2
        bonds.append(
            LayoutBond(
                a1=bond.GetBeginAtomIdx() + 1,
                a2=bond.GetEndAtomIdx() + 1,
                order=int(bond.GetBondTypeAsDouble()),
                stereo=stereo,
            )
        )
    return SketchLayout(atoms=atoms, bonds=bonds)


def cleanup_coords(
    atoms: list[SketchAtom], bonds: list[SketchBond]
) -> dict[int, tuple[float, float]]:
    """Recompute the layout with rdDepictor; the topology is never touched.

    Returns original atom id -> (x, y) in Angstrom on the **chemical frame**
    (y grows upward): only the canvas knows the view it wants to centre on, so
    the y flip and the pixel conversion stay client-side.  ``build_mol`` already
    constructs a fresh molecule, which is the "on a copy" rule ``depict.py``
    follows.  rdDepictor choking on an exotic graph is a 422 with a human
    reason — a 500 would take down a convenience button.
    """
    mol, _ = build_mol(atoms, bonds)
    try:
        AllChem.Compute2DCoords(mol, canonOrient=True)
    except Exception as exc:  # rdDepictor raising is a user-facing verdict, not a crash
        log.debug("sketch cleanup failed", exc_info=True)
        raise InvalidInputError(f"无法重排该结构：{brief_error(exc)}") from None

    _scale_bond_lengths(mol)

    conf = mol.GetConformer()
    positions: dict[int, tuple[float, float]] = {}
    for atom in mol.GetAtoms():
        point = conf.GetAtomPosition(atom.GetIdx())
        positions[int(atom.GetProp(_ID_PROP))] = (point.x, point.y)
    return positions
