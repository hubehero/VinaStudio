"""BUTINA clustering of docked poses (smina's clustering algorithm).

Answers "how many distinct binding modes does this pose list contain" by
grouping poses whose symmetry-corrected heavy-atom RMSD falls within
``cutoff``. Distances come exclusively from ``rmsd.rmsd_between`` — one
GetBestRMS path shared with redocking RMSD, never a second copy of the
algorithm (task book §8).

The representative (``centroid_index``) is the member with the smallest mean
distance to the other members — geometric representativeness, deliberately
**not** the lowest-energy pose: energy order and geometric redundancy are
different questions, and picking by energy would re-introduce the very
duplicates clustering is meant to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from rdkit import Chem

from vinastudio.core.chem.rmsd import rmsd_between

#: Community convention (same as RMSD success threshold), not a hard limit.
DEFAULT_CLUSTER_CUTOFF = 2.0


@dataclass(slots=True)
class Cluster:
    """One cluster of geometrically similar poses (0-based pose indices)."""

    member_indices: list[int]
    centroid_index: int
    max_diameter: float
    #: Mean RMSD of members to the centroid — how tight the shown
    #: representative actually is for its group.
    mean_rmsd: float

    @property
    def size(self) -> int:
        return len(self.member_indices)


def cluster_poses(pose_mols: list[Chem.Mol], cutoff: float = DEFAULT_CLUSTER_CUTOFF) -> list[Cluster]:
    """Group *pose_mols* by BUTINA clustering at *cutoff* ångström.

    BUTINA: rank points by neighbour count (``distance <= cutoff``), then
    repeatedly seed a cluster from the highest-ranked unassigned point and
    pull in all its still-unassigned neighbours. O(n²) distance matrix —
    20×20 poses are trivially cheap.

    Input molecules are never mutated: ``rmsd_between`` copies internally.
    """
    n = len(pose_mols)
    if n == 0:
        return []
    dist = _distance_matrix(pose_mols)
    neighbours = [
        [j for j in range(n) if j != i and dist[i][j] <= cutoff]
        for i in range(n)
    ]
    # Seed order: most neighbours first; stable sort keeps index order on ties.
    order = sorted(range(n), key=lambda i: -len(neighbours[i]))

    assigned = [False] * n
    clusters: list[Cluster] = []
    for seed in order:
        if assigned[seed]:
            continue
        members = [seed, *(j for j in neighbours[seed] if not assigned[j])]
        for index in members:
            assigned[index] = True
        clusters.append(_build_cluster(members, dist))
    return clusters


def _distance_matrix(mols: list[Chem.Mol]) -> list[list[float]]:
    n = len(mols)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            value = rmsd_between(mols[j], mols[i])
            matrix[i][j] = value
            matrix[j][i] = value
    return matrix


def _build_cluster(members: list[int], dist: list[list[float]]) -> Cluster:
    if len(members) == 1:
        return Cluster(member_indices=members, centroid_index=members[0],
                       max_diameter=0.0, mean_rmsd=0.0)

    def mean_to_others(index: int) -> float:
        return mean(dist[index][other] for other in members if other != index)

    centroid = min(members, key=mean_to_others)
    pairs = [dist[members[a]][members[b]]
             for a in range(len(members)) for b in range(a + 1, len(members))]
    return Cluster(
        member_indices=members,
        centroid_index=centroid,
        max_diameter=max(pairs),
        mean_rmsd=mean(dist[m][centroid] for m in members),
    )
