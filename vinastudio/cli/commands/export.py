"""``export``: SDF/PDBQT artifacts and interop views of a result."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from vinastudio.api.result import (
    artifact_path,
    read_result_document,
    write_json_atomic,
)
from vinastudio.cli.errors import InputError
from vinastudio.core.chem.export import pdbqt_to_pdb
from vinastudio.core.exporters import (
    chimerax_script,
    complex_pdb,
    plip_document,
    pymol_script,
    split_sdf_pose,
)

_COPY_FORMATS = {"sdf": "posesSdf", "pdbqt": "posesPdbqt"}
_ALL_FORMATS = {*_COPY_FORMATS, "complex-pdb", "pml", "cxc", "plip-json"}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "export", help="copy poses and write complex/PML/CXC/PLIP views"
    )
    parser.add_argument("--result", required=True, help="result.json path")
    parser.add_argument(
        "--format",
        default="sdf,pdbqt",
        help="sdf,pdbqt,complex-pdb,pml,cxc,plip-json",
    )
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--pose",
        type=int,
        default=None,
        help="1-based pose for complex/pml/cxc/plip (default 1)",
    )
    parser.add_argument(
        "--cutoff",
        type=float,
        default=4.0,
        help="contact search radius for plip-json (Angstrom)",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.set_defaults(handler=run)


def _receptor_text(document, result_path: Path) -> str:
    pdb = artifact_path(document, "receptorPdb", result_path)
    if pdb is not None and pdb.is_file():
        return pdb.read_text(encoding="utf-8")
    pdbqt = artifact_path(document, "receptorPdbqt", result_path)
    if pdbqt is not None and pdbqt.is_file():
        return pdbqt_to_pdb(pdbqt)
    raise InputError("result has no receptor PDB/PDBQT artifact")


def _receptor_file(document, result_path: Path) -> Path:
    pdb = artifact_path(document, "receptorPdb", result_path)
    if pdb is not None and pdb.is_file():
        return pdb
    pdbqt = artifact_path(document, "receptorPdbqt", result_path)
    if pdbqt is not None and pdbqt.is_file():
        return pdbqt
    raise InputError("result has no receptor PDB/PDBQT artifact")


def _pose_text(document, result_path: Path, pose: int, *, split: bool) -> str:
    source = artifact_path(document, "posesSdf", result_path)
    if source is None or not source.is_file():
        raise InputError("result has no poses.sdf artifact")
    text = source.read_text(encoding="utf-8")
    return split_sdf_pose(text, pose) if split else text


def run(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    result_path = Path(args.result).expanduser().resolve()
    document = read_result_document(result_path)
    output = Path(args.out).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    requested = [item.strip().lower() for item in args.format.split(",") if item.strip()]
    unknown = [item for item in requested if item not in _ALL_FORMATS]
    if unknown:
        raise InputError(f"unknown format(s): {', '.join(unknown)}")
    if args.pose is not None and "pdbqt" in requested:
        raise InputError("--pose is only supported for SDF/complex formats")

    interop = {"complex-pdb", "pml", "cxc", "plip-json"} & set(requested)
    pose = args.pose or 1
    if interop and pose < 1:
        raise InputError("--pose must be >= 1")
    pose_text = (
        _pose_text(document, result_path, pose, split=bool(interop))
        if interop or "sdf" in requested
        else ""
    )

    outputs: dict[str, str] = {}
    complex_path = output / "complex.pdb"
    if interop:
        complex_path.write_text(
            complex_pdb(_receptor_text(document, result_path), pose_text),
            encoding="utf-8",
        )
        outputs["complex-pdb"] = str(complex_path)

    for fmt in requested:
        if fmt in _COPY_FORMATS:
            source = artifact_path(document, _COPY_FORMATS[fmt], result_path)
            if source is None or not source.is_file():
                raise InputError(f"result has no {fmt} poses artifact")
            if args.pose is not None and fmt == "sdf":
                target = output / f"pose-{args.pose}.sdf"
                target.write_text(
                    split_sdf_pose(source.read_text(encoding="utf-8"), args.pose)
                    + "$$$$\n",
                    encoding="utf-8",
                )
            else:
                target = output / f"poses.{fmt}"
                shutil.copyfile(source, target)
            outputs[fmt] = str(target)
        elif fmt == "pml":
            target = output / "complex.pml"
            target.write_text(pymol_script("complex"), encoding="utf-8")
            outputs[fmt] = str(target)
        elif fmt == "cxc":
            target = output / "complex.cxc"
            target.write_text(chimerax_script("complex"), encoding="utf-8")
            outputs[fmt] = str(target)
        elif fmt == "plip-json":
            target = output / "interactions.plip.json"
            write_json_atomic(
                target,
                plip_document(
                    _receptor_file(document, result_path),
                    pose_text,
                    distance_cutoff=args.cutoff,
                ),
            )
            outputs[fmt] = str(target)

    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "export",
        "resultPath": str(result_path),
        "pose": pose if interop else args.pose,
        "outputs": outputs,
    }
    return payload, "\n".join(f"{name}: {path}" for name, path in outputs.items())
