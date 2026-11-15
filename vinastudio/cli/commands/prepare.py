"""``prepare receptor|ligand``: write PDBQT/SDF artifacts and a report."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vinastudio.api.prepare import prepare_ligand, prepare_receptor
from vinastudio.api.result import write_json_atomic
from vinastudio.cli.errors import InputError
from vinastudio.core.chem.ligand_prep import LigandPrepOptions
from vinastudio.core.chem.receptor_prep import ReceptorPrepOptions


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "prepare", help="prepare a receptor or ligand into docking artifacts"
    )
    kinds = parser.add_subparsers(dest="kind", required=True)

    receptor = kinds.add_parser("receptor", help="prepare a receptor")
    receptor.add_argument("-i", "--input", required=True, help="receptor PDB/mmCIF")
    receptor.add_argument("-o", "--out", required=True, help="output directory")
    receptor.add_argument("--json", action="store_true", help="emit a JSON envelope")
    receptor.add_argument("--altloc", default="", help="default alternate location")
    receptor.add_argument("--keep-residue", action="append", default=[], metavar="KEY")
    receptor.add_argument("--flex-residue", action="append", default=[], metavar="KEY")
    receptor.add_argument("--allow-bad-residues", action="store_true")
    receptor.add_argument(
        "--no-normalise-atom-order",
        dest="normalise_atom_order",
        action="store_false",
        default=True,
    )
    waters = receptor.add_mutually_exclusive_group()
    waters.add_argument("--delete-waters", dest="delete_waters", action="store_true", default=True)
    waters.add_argument("--keep-waters", dest="delete_waters", action="store_false")
    hetero = receptor.add_mutually_exclusive_group()
    hetero.add_argument("--delete-hetero", dest="delete_hetero", action="store_true", default=True)
    hetero.add_argument("--keep-hetero", dest="delete_hetero", action="store_false")
    receptor.set_defaults(handler=_run_receptor)

    ligand = kinds.add_parser("ligand", help="prepare a ligand")
    ligand.add_argument("-i", "--input", required=True, help="ligand SDF/mol/SMILES file")
    ligand.add_argument("-o", "--out", required=True, help="output directory")
    ligand.add_argument("--json", action="store_true", help="emit a JSON envelope")
    ligand.add_argument("--embed-seed", type=int, default=42)
    ligand.add_argument("--no-optimise", dest="optimise", action="store_false", default=True)
    ligand.add_argument("--rigid-macrocycles", action="store_true")
    ligand.add_argument("--flexible-amides", action="store_true")
    ligand.add_argument("--hydrate", action="store_true")
    ligand.add_argument("--double-bond-penalty", type=float, default=50.0)
    ligand.set_defaults(handler=_run_ligand)


def _run_receptor(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    source = Path(args.input).expanduser()
    if not source.is_file():
        raise InputError(f"receptor not found: {source}")
    output = Path(args.out).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    options = ReceptorPrepOptions(
        delete_waters=args.delete_waters,
        delete_hetero=args.delete_hetero,
        allow_bad_residues=args.allow_bad_residues,
        normalise_atom_order=args.normalise_atom_order,
        default_altloc=args.altloc,
        keep_residues=tuple(args.keep_residue),
        flexible_residues=tuple(args.flex_residue),
    )
    preparation = prepare_receptor(source, options)
    outputs = {
        "pdbqt": str(_write(output / "receptor.pdbqt", preparation.pdbqt)),
        "pdb": str(_write(output / "receptor.pdb", preparation.pdb)),
    }
    if preparation.flex_pdbqt:
        outputs["flexPdbqt"] = str(_write(output / "flex.pdbqt", preparation.flex_pdbqt))
    report_path = write_json_atomic(
        output / "receptor-report.json", asdict(preparation.report)
    )
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "prepare",
        "kind": "receptor",
        "outputs": outputs,
        "reportPath": str(report_path),
    }
    return payload, "\n".join([f"{name}: {path}" for name, path in outputs.items()])


def _run_ligand(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    source = Path(args.input).expanduser()
    if not source.is_file():
        raise InputError(f"ligand not found: {source}")
    output = Path(args.out).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    options = LigandPrepOptions(
        optimise_geometry=args.optimise,
        embed_seed=args.embed_seed,
        rigid_macrocycles=args.rigid_macrocycles,
        flexible_amides=args.flexible_amides,
        hydrate=args.hydrate,
        double_bond_penalty=args.double_bond_penalty,
    )
    preparation = prepare_ligand(source, options)
    outputs = {
        "pdbqt": str(_write(output / "ligand.pdbqt", preparation.pdbqt)),
        "sdf": str(_write(output / "ligand.sdf", preparation.sdf)),
    }
    report_path = write_json_atomic(
        output / "ligand-report.json", asdict(preparation.report)
    )
    payload = {
        "schemaVersion": "1.0",
        "ok": True,
        "command": "prepare",
        "kind": "ligand",
        "outputs": outputs,
        "reportPath": str(report_path),
    }
    return payload, "\n".join([f"{name}: {path}" for name, path in outputs.items()])


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
