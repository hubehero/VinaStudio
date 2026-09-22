"""The batch CSV must count the poses the run actually produced.

The pose_count column used to read ``len(energies)`` while batch rows carry
``nPoses``, so every export reported 0 poses for every ligand.
"""

from __future__ import annotations

import csv
import io

from vinastudio.server.routers.docking import _batch_csv_text


def _rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_pose_count_comes_from_n_poses() -> None:
    text = _batch_csv_text([
        {"ligandIndex": 0, "label": "lig-a", "status": "completed",
         "bestAffinity": -8.5, "nPoses": 7, "error": ""},
        {"ligandIndex": 1, "label": "lig-b", "status": "failed", "error": "boom"},
    ])

    rows = _rows(text)
    assert rows[0]["pose_count"] == "7"
    assert rows[0]["best_affinity_kcal_mol"] == "-8.5"
    assert rows[1]["pose_count"] == "0"
    assert rows[1]["error"] == "boom"


def test_the_header_keeps_the_documented_column_names() -> None:
    header = _batch_csv_text([]).splitlines()[0]
    assert header == (
        "ligand_index,label,status,best_affinity_kcal_mol,pose_count,error"
    )
