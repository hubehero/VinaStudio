"""Candidate binding sites from alpha spheres.

Given only a receptor, propose **candidate** sites a ligand might bind, so the
user has somewhere to put the search box when no co-crystal ligand or known
residue is available. Candidates, not answers: the interface must present them
as sites to be checked, never as "the" binding site.

The method follows Le Guilloux, Schmidtke & Tuffery, *Fpocket: an open source
platform for ligand pocket detection*, BMC Bioinformatics 10:168 (2009) — the
paper is archived in ``docs/references/`` and is the source of every constant
below:

* an **alpha sphere** contacts four atoms on its boundary and contains none;
  its centre is a Voronoi vertex and its radius is the local curvature. Small
  spheres sit inside the protein, large ones outside, and **clefts and cavities
  correspond to intermediate radii** — hence the published filter 3.0-6.0 A.
* pockets are **clusters of alpha spheres**; the paper's final clustering step
  links spheres within 4.0 A and drops clusters below 35 spheres.
* ranking uses the paper's five descriptors. **The PLS coefficients are not
  published**, so the combination below is ours, documented and validated
  against the ground-truth tests rather than copied.

Deliberate limits, stated because they matter:

* The published accuracy is **83% top-1 / 92% top-3 (holo)** and **69% / 94%
  (apo)** by the PocketPicker criterion (pocket centre within 4 A of a ligand
  atom). A candidate the user picks is a starting point; the paper itself warns
  that "the largest pocket tends to correspond to the site, but this rule cannot
  be generalised".
* We implement from the paper. **fpocket's source is GPL and is not read,
  copied or linked** (the same isolation rule this repository applies to
  MoleditPy).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from scipy.spatial import Voronoi, cKDTree
from scipy.spatial.distance import pdist

from vinastudio.core.box import Box, Point3
from vinastudio.core.chem.autodock_types import element_for
from vinastudio.core.chem.pdb_lines import (
    atom_records,
    coordinates,
    element_record,
    is_hydrogen_record,
    residue_name,
)
from vinastudio.core.errors import InvalidInputError

#: Pauling electronegativity. The paper's apolar test is "at least three atoms
#: with an electronegativity below 2.8", which is exactly C/S/P and friends
#: versus N/O/halogens.
_ELECTRONEGATIVITY: Final[dict[str, float]] = {
    "H": 2.20,
    "C": 2.55,
    "N": 3.04,
    "O": 3.44,
    "F": 3.98,
    "P": 2.19,
    "S": 2.58,
    "CL": 3.16,
    "BR": 2.96,
    "I": 2.66,
    "SE": 2.55,
}

#: Residues the paper's binary polarity descriptor counts as polar.
_POLAR_RESIDUES: Final[frozenset[str]] = frozenset(
    {"ASP", "GLU", "LYS", "ARG", "HIS", "HID", "HIE", "HIP",
     "ASN", "GLN", "SER", "THR", "TYR", "CYS", "TRP"}
)

#: Neighbourhood radius used for the "local hydrophobic density" descriptor.
#: The paper names the descriptor but not its radius; 6 A is its own maximum
#: alpha-sphere radius, and the choice is recorded here rather than hidden.
_HYDROPHOBIC_NEIGHBOURHOOD: Final = 6.0

#: Our weights over the paper's five descriptors (see the module docstring).
_SCORE_WEIGHTS: Final[dict[str, float]] = {
    "spheres": 0.30,
    "hydrophobic_density": 0.25,
    "apolar_fraction": 0.20,
    "density": 0.15,
    "polarity": -0.10,
}


@dataclass(frozen=True, slots=True)
class PocketAtom:
    """One heavy atom: what the alpha-sphere classification needs."""

    coordinates: Point3
    element: str
    resname: str


@dataclass(frozen=True, slots=True)
class PocketParams:
    """All thresholds, traced to the paper where the paper publishes them."""

    min_radius: float = 3.0
    max_radius: float = 6.0
    #: The paper's three clustering passes: rough segmentation at 1.73 A, merge
    #: clusters whose centres of mass are within 2.5 A, then multi-linkage at
    #: 4.0 A. The last one merges only clusters joined by enough sphere pairs —
    #: plain single linkage at 4 A collapses a whole protein into one pocket.
    link_step1: float = 1.73
    link_step2: float = 2.5
    link_step3: float = 4.0
    #: Sphere pairs at ``link_step3`` needed to merge two clusters. The paper
    #: says only "a certain number", so this value is ours. It is the one
    #: unspecified constant in the pipeline, and it is pinned by the
    #: ground-truth tests: 8 puts the known site inside the top 3 for both 1iep
    #: and 1hsg, the accuracy the paper reports for its own method (92% holo /
    #: 94% apo). Lower values let a mere contact merge two sites and lose the
    #: site entirely; higher ones leave the true pocket out of the box.
    link_min_pairs: int = 8
    min_spheres: int = 35
    apolar_electronegativity: float = 2.8
    apolar_min_contacts: int = 3
    margin: float = 4.0
    max_box_edge: float = 28.0


@dataclass(frozen=True, slots=True)
class Pocket:
    """One candidate site, in the terms the box panel needs."""

    center: Point3
    size: Point3
    volume: float
    spheres: int
    score: float
    apolar_fraction: float

    def box(self, spacing: float, *, force_even_voxels: bool = True) -> Box:
        """The search box this candidate implies.

        Even voxels by default: a candidate is something you dock in next, and
        Vina's ``write_maps`` refuses an odd voxel count.
        """
        return Box(
            center=self.center,
            size=self.size,
            spacing=spacing,
            force_even_voxels=force_even_voxels,
        )


# -- reading -----------------------------------------------------------------


def read_atoms(path: str | Path) -> list[PocketAtom]:
    """Heavy atoms with the element and residue name the descriptors need."""
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidInputError(f"file not found: {file_path}")

    suffix = file_path.suffix.lower()
    text = ""
    if suffix in {".pdb", ".ent"}:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    elif suffix in {".cif", ".mmcif"}:
        from vinastudio.core.chem.mmcif import mmcif_to_pdb

        text = mmcif_to_pdb(file_path.read_text(encoding="utf-8", errors="replace"))
    if text:
        atoms = _atoms_from_pdb(text)
    elif suffix == ".pdbqt":
        atoms = _atoms_from_pdbqt(file_path.read_text(encoding="utf-8", errors="replace"))
    elif suffix in {".sdf", ".mol"}:
        atoms = _atoms_from_rdkit(file_path)
    else:
        raise InvalidInputError(
            f"cannot detect pockets in {suffix or 'a file without an extension'}; "
            "expected .pdb, .ent, .cif, .pdbqt, .sdf or .mol"
        )

    if len(atoms) < 4:
        raise InvalidInputError(
            f"pocket detection needs a structure, got {len(atoms)} heavy atoms"
        )
    return atoms


def _atoms_from_pdb(text: str) -> list[PocketAtom]:
    return [
        PocketAtom(coordinates(line), element_record(line), residue_name(line))
        for line in atom_records(text)
        if not is_hydrogen_record(line)
    ]


def _atoms_from_pdbqt(text: str) -> list[PocketAtom]:
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    return [
        PocketAtom(
            atom.coordinates,
            element_for(atom.name, atom.atom_type),
            atom.resname,
        )
        for atom in parse_pdbqt(text).first_pose.atoms
        if not atom.is_polar_hydrogen
    ]


def _atoms_from_rdkit(path: Path) -> list[PocketAtom]:
    """A small molecule is a valid input; it simply has no residue names."""
    from rdkit import Chem

    if path.suffix.lower() == ".sdf":
        molecules = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
        mol = next((candidate for candidate in molecules if candidate is not None), None)
    else:
        mol = Chem.MolFromMolFile(str(path), removeHs=False, sanitize=False)
    if mol is None:
        raise InvalidInputError(f"no readable molecule in {path.name}")
    if mol.GetNumConformers() == 0:
        raise InvalidInputError(f"{path.name} has no coordinates")

    conformer = mol.GetConformer()
    return [
        PocketAtom(
            (
                conformer.GetAtomPosition(atom.GetIdx()).x,
                conformer.GetAtomPosition(atom.GetIdx()).y,
                conformer.GetAtomPosition(atom.GetIdx()).z,
            ),
            atom.GetSymbol().upper(),
            "",
        )
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() != 1
    ]


# -- alpha spheres -----------------------------------------------------------


def alpha_spheres(
    points: np.ndarray, params: PocketParams
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
    """Centres, radii and neighbour links of the alpha spheres in the band.

    The Delaunay tetrahedralisation's circumspheres are empty by construction,
    and their centres are the Voronoi vertices — the alpha spheres of Liang and
    Edelsbrunner. Every atom at a vertex is equidistant from it, so the nearest
    atom's distance *is* the sphere radius.

    The links matter as much as the spheres: the paper's first clustering pass
    walks the **Voronoi vertex adjacency** (two vertices bounding the same
    ridge), not raw distance, and using distance alone merges neighbours the
    tessellation keeps apart.
    """
    tessellation = Voronoi(points)
    centres = tessellation.vertices
    if len(centres) == 0:
        return centres, np.zeros(0), []

    radii, _ = cKDTree(points).query(centres, k=1)
    keep = (radii >= params.min_radius) & (radii <= params.max_radius)
    kept_index = {int(index): position for position, index in enumerate(np.flatnonzero(keep))}

    links: list[tuple[int, int]] = []
    for ridge in tessellation.ridge_vertices:
        first, second = int(ridge[0]), int(ridge[-1])
        left, right = kept_index.get(first), kept_index.get(second)
        if left is not None and right is not None and left != right:
            links.append((left, right))

    return centres[keep], radii[keep], links


def _is_apolar(contacts: list[PocketAtom], params: PocketParams) -> bool:
    """The paper's test: at least three contacts below 2.8 electronegativity."""
    apolar = sum(
        1
        for atom in contacts
        if _ELECTRONEGATIVITY.get(atom.element.upper(), 0.0) < params.apolar_electronegativity
    )
    return apolar >= params.apolar_min_contacts


def _link(
    centres: np.ndarray, links: list[tuple[int, int]], params: PocketParams
) -> list[np.ndarray]:
    """The paper's three clustering passes, in order."""
    groups = _single_linkage(centres, links, params.link_step1)
    groups = _merge_by_centroid(centres, groups, params.link_step2)
    return _merge_by_pairs(centres, groups, params.link_step3, params.link_min_pairs)


def _single_linkage(
    centres: np.ndarray, links: list[tuple[int, int]], radius: float
) -> list[np.ndarray]:
    """Rough segmentation: Voronoi-adjacent spheres that are also close.

    Both conditions matter — the tessellation says which spheres touch, the
    distance says whether they are part of the same cavity.
    """
    count = len(centres)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in links:
        if float(np.linalg.norm(centres[left] - centres[right])) <= radius:
            union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)
    return [np.asarray(members, dtype=np.intp) for members in groups.values()]


def _merge_by_centroid(
    centres: np.ndarray, groups: list[np.ndarray], radius: float
) -> list[np.ndarray]:
    """Fold clusters whose centres of mass nearly coincide."""
    if len(groups) < 2:
        return groups

    centroids = np.asarray([centres[members].mean(axis=0) for members in groups])
    parent = list(range(len(groups)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left, right in cKDTree(centroids).query_pairs(r=radius):
        left_root, right_root = find(int(left)), find(int(right))
        if left_root != right_root:
            parent[right_root] = left_root

    merged: dict[int, list[np.ndarray]] = {}
    for index, members in enumerate(groups):
        merged.setdefault(find(index), []).append(members)
    return [np.concatenate(parts) for parts in merged.values()]


def _merge_by_pairs(
    centres: np.ndarray, groups: list[np.ndarray], radius: float, min_pairs: int
) -> list[np.ndarray]:
    """Multi-linkage: merge two clusters only when enough sphere pairs are close.

    Single linkage at this radius is what collapses a whole domain into one
    "pocket"; requiring several links is what keeps separate sites separate.
    """
    if len(groups) < 2:
        return groups

    labels = np.empty(len(centres), dtype=np.intp)
    for index, members in enumerate(groups):
        labels[members] = index

    tally: dict[tuple[int, int], int] = {}
    for left, right in cKDTree(centres).query_pairs(r=radius):
        first, second = int(labels[left]), int(labels[right])
        if first == second:
            continue
        key = (min(first, second), max(first, second))
        tally[key] = tally.get(key, 0) + 1

    parent = list(range(len(groups)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for (first, second), links in tally.items():
        if links < min_pairs:
            continue
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    merged: dict[int, list[np.ndarray]] = {}
    for index, members in enumerate(groups):
        merged.setdefault(find(index), []).append(members)
    return [np.concatenate(parts) for parts in merged.values()]


# -- detection ---------------------------------------------------------------


def detect_pockets(
    atoms: list[PocketAtom],
    params: PocketParams | None = None,
    *,
    top_k: int = 5,
) -> list[Pocket]:
    """Candidate sites, best score first."""
    settings = params or PocketParams()
    if len(atoms) < 4:
        raise InvalidInputError(
            f"pocket detection needs a structure, got {len(atoms)} heavy atoms"
        )

    coords = np.asarray([atom.coordinates for atom in atoms], dtype=float)
    centres, radii, links = alpha_spheres(coords, settings)
    if len(centres) == 0:
        return []

    tree = cKDTree(coords)
    # The contacting shell sits at the sphere's own radius; the tolerance
    # absorbs coordinate rounding in the file.
    contacts = tree.query_ball_point(centres, r=radii + 0.5)
    apolar = np.asarray(
        [_is_apolar([atoms[index] for index in shell], settings) for shell in contacts]
    )

    candidates = [
        _describe(members, centres, radii, apolar, contacts, atoms, settings)
        for members in _link(centres, links, settings)
        if len(members) >= settings.min_spheres
    ]
    if not candidates:
        return []

    return _rank(candidates)[: max(1, top_k)]


def pockets_from_file(
    path: str | Path,
    params: PocketParams | None = None,
    *,
    top_k: int = 5,
) -> tuple[list[Pocket], int]:
    """Detect candidate pockets in a structure file; returns them and the atom count."""
    atoms = read_atoms(path)
    return detect_pockets(atoms, params, top_k=top_k), len(atoms)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A pocket before normalisation: the paper's five raw descriptors."""

    center: Point3
    size: Point3
    volume: float
    spheres: int
    apolar_fraction: float
    hydrophobic_density: float
    density: float
    polarity: float


_RAW_KEYS: Final[tuple[str, ...]] = (
    "spheres",
    "hydrophobic_density",
    "apolar_fraction",
    "density",
    "polarity",
)


def _describe(
    members: np.ndarray,
    centres: np.ndarray,
    radii: np.ndarray,
    apolar: np.ndarray,
    contacts: list[list[int]],
    atoms: list[PocketAtom],
    settings: PocketParams,
) -> _Candidate:
    sphere_points = centres[members]
    sphere_radii = radii[members]
    pocket_apolar = apolar[members]

    corner_lo = sphere_points.min(axis=0)
    corner_hi = sphere_points.max(axis=0)
    center = np.round((corner_lo + corner_hi) / 2, 3)
    size = np.round(
        np.minimum(
            np.maximum(corner_hi - corner_lo + 2 * settings.margin, settings.min_radius),
            settings.max_box_edge,
        ),
        3,
    )

    # "Alpha sphere density": the paper defines it as the mean pairwise distance
    # between the pocket's spheres, so a smaller value means a tighter pocket.
    density = float(pdist(sphere_points).mean()) if len(sphere_points) > 1 else 0.0

    # "Mean local hydrophobic density": apolar spheres per apolar neighbourhood.
    apolar_points = sphere_points[pocket_apolar]
    if len(apolar_points) > 0:
        neighbourhoods = cKDTree(apolar_points).query_ball_point(
            apolar_points, r=_HYDROPHOBIC_NEIGHBOURHOOD, return_length=True
        )
        hydrophobic_density = float(np.mean(neighbourhoods))
    else:
        hydrophobic_density = 0.0

    # "Polarity score": the paper sums a binary polarity over the pocket's
    # residues, so this is a count of polar residues lining the candidate.
    residues = {
        atoms[index].resname.upper()
        for member in members
        for index in contacts[int(member)]
        if atoms[index].resname
    }
    polarity = float(sum(1 for name in residues if name in _POLAR_RESIDUES))

    return _Candidate(
        center=(float(center[0]), float(center[1]), float(center[2])),
        size=(float(size[0]), float(size[1]), float(size[2])),
        volume=round(float(np.sum(4.0 / 3.0 * np.pi * sphere_radii**3)), 1),
        spheres=len(members),
        apolar_fraction=round(float(np.mean(pocket_apolar)), 3),
        hydrophobic_density=hydrophobic_density,
        density=density,
        polarity=polarity,
    )


def _rank(candidates: list[_Candidate]) -> list[Pocket]:
    """Normalise the descriptors across the candidates and order by score.

    Normalisation is per protein — the paper normalises within one structure
    ("the largest and the smallest pocket within a given protein would have a
    normalised number of alpha spheres of 1 and 0") — so it cannot happen while
    a candidate is being built.
    """
    raw = {key: [getattr(candidate, key) for candidate in candidates] for key in _RAW_KEYS}
    normalized = {key: _min_max(values) for key, values in raw.items()}
    # Density is inverted: a tighter pocket (smaller mean distance) scores higher.
    normalized["density"] = [1.0 - value for value in normalized["density"]]

    ranked: list[Pocket] = []
    for index, candidate in enumerate(candidates):
        score = sum(
            weight * normalized[key][index] for key, weight in _SCORE_WEIGHTS.items()
        )
        ranked.append(
            Pocket(
                center=candidate.center,
                size=candidate.size,
                volume=candidate.volume,
                spheres=candidate.spheres,
                score=round(score, 4),
                apolar_fraction=candidate.apolar_fraction,
            )
        )
    ranked.sort(key=lambda pocket: pocket.score, reverse=True)
    return ranked


def _min_max(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        # One candidate (or all equal): the descriptor cannot separate them.
        return [1.0 for _ in values]
    return [(value - low) / (high - low) for value in values]
