"""Documentation tables that state numbers the code owns must keep matching.

The weights table in `docs/VINA_API_COVERAGE.md` listed five values for AutoDock4
while the code requires six, which is exactly the kind of drift a reader cannot
spot. These tests parse the tables instead of trusting them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vinastudio.config import SCORING_WEIGHT_COUNT

REPO_ROOT = Path(__file__).resolve().parents[2]
COVERAGE = REPO_ROOT / "docs" / "VINA_API_COVERAGE.md"

#: | `vina` | 7 | `-0.035579 -0.005156 ...` |
_WEIGHT_ROW = re.compile(
    r"^\|\s*`(?P<name>\w+)`\s*\|\s*(?P<count>\d+)\s*\|\s*`(?P<values>[^`]+)`\s*\|\s*$",
    re.MULTILINE,
)


def _weight_rows() -> dict[str, tuple[int, list[str]]]:
    rows: dict[str, tuple[int, list[str]]] = {}
    for match in _WEIGHT_ROW.finditer(COVERAGE.read_text(encoding="utf-8")):
        name = match.group("name")
        if name in SCORING_WEIGHT_COUNT:
            rows[name] = (int(match.group("count")), match.group("values").split())
    return rows


def test_the_table_lists_every_scoring_function() -> None:
    assert set(_weight_rows()) == set(SCORING_WEIGHT_COUNT)


@pytest.mark.parametrize("scoring", sorted(SCORING_WEIGHT_COUNT))
def test_documented_weight_count_matches_the_code(scoring: str) -> None:
    count, values = _weight_rows()[scoring]

    assert count == SCORING_WEIGHT_COUNT[scoring], (
        f"{scoring} advertises {count} weights, the code requires "
        f"{SCORING_WEIGHT_COUNT[scoring]}"
    )
    assert len(values) == count, (
        f"{scoring} lists {len(values)} values for a stated count of {count}"
    )
