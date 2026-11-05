"""BUTINA's greedy partition over a square distance matrix.

Both docked-pose clustering (RMSD distances) and interaction-fingerprint
clustering (Tanimoto distances) need exactly this step. Keeping one
implementation means a change to the seed/neighbour rule cannot make the two
features disagree.
"""

from __future__ import annotations


def butina_partition(
    distances: list[list[float]], cutoff: float
) -> list[list[int]]:
    """Group indices by BUTINA: neighbours within cutoff, seed most connected.

    Seed order is the neighbour count descending, with a stable sort so ties
    keep index order. Each seed pulls in its still-unassigned neighbours.
    """
    n = len(distances)
    if n == 0:
        return []
    neighbours = [
        [j for j in range(n) if j != i and distances[i][j] <= cutoff]
        for i in range(n)
    ]
    order = sorted(range(n), key=lambda i: -len(neighbours[i]))

    assigned = [False] * n
    clusters: list[list[int]] = []
    for seed in order:
        if assigned[seed]:
            continue
        members = [seed, *(j for j in neighbours[seed] if not assigned[j])]
        for index in members:
            assigned[index] = True
        clusters.append(members)
    return clusters
