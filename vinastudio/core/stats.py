"""Small, dependency-free statistics used by validation and screening reports.

These are descriptive summaries of a fixed dataset, not claims of universal
accuracy. The helpers are here rather than in a script so the benchmark report
and the screening metrics use the same interval calculation.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Sequence


def bootstrap_ci(
    values: Sequence[float],
    *,
    n: int = 2000,
    seed: int = 42,
) -> tuple[float, float] | None:
    """Percentile bootstrap 95% interval for the mean; ``None`` for n < 2."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = [
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(n)
    ]
    means.sort()
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.96,
) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion; ``None`` for total 0."""
    if total <= 0:
        return None
    failures = total - successes
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(p * failures / total + z * z / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def bootstrap_metric_ci[T](
    rows: Sequence[T],
    metric: Callable[[Sequence[T]], float | None],
    *,
    n: int = 1000,
    seed: int = 42,
) -> tuple[float, float] | None:
    """Bootstrap 95% interval for an arbitrary metric over rows.

    Resamples rows with replacement. A resample for which the metric returns
    ``None`` is skipped; if fewer than 95% of resamples are usable, the
    interval is not reported rather than being computed from a biased subset.
    """
    if len(rows) < 2:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(n):
        sample = [rng.choice(rows) for _ in rows]
        value = metric(sample)
        if value is not None and math.isfinite(value):
            values.append(value)
    if len(values) < int(0.95 * n):
        return None
    values.sort()
    return (values[int(0.025 * len(values))], values[int(0.975 * len(values))])
