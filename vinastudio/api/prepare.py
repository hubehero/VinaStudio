"""Stable preparation API used by the CLI and scripts; no Qt or HTTP imports."""

from __future__ import annotations

from pathlib import Path

from vinastudio.core.chem.ligand_prep import (
    LigandPreparation,
    LigandPrepOptions,
)
from vinastudio.core.chem.ligand_prep import (
    prepare_ligand as _prepare_ligand,
)
from vinastudio.core.chem.receptor_prep import (
    ReceptorPreparation,
    ReceptorPrepOptions,
)
from vinastudio.core.chem.receptor_prep import (
    prepare_receptor as _prepare_receptor,
)
from vinastudio.schemas.job import (
    LigandPreparationOptions,
    ReceptorPreparationOptions,
)


def prepare_receptor(
    path: str | Path,
    options: ReceptorPrepOptions | None = None,
) -> ReceptorPreparation:
    return _prepare_receptor(path, options)


def prepare_ligand(
    path: str | Path,
    options: LigandPrepOptions | None = None,
) -> LigandPreparation:
    return _prepare_ligand(path, options)


def receptor_options_from_schema(
    options: ReceptorPreparationOptions,
) -> ReceptorPrepOptions:
    return ReceptorPrepOptions(
        delete_waters=options.deleteWaters,
        delete_hetero=options.deleteHetero,
        allow_bad_residues=options.allowBadResidues,
        normalise_atom_order=options.normaliseAtomOrder,
        default_altloc=options.defaultAltloc,
        keep_residues=tuple(options.keepResidues),
        flexible_residues=tuple(options.flexibleResidues),
    )


def ligand_options_from_schema(
    options: LigandPreparationOptions,
) -> LigandPrepOptions:
    return LigandPrepOptions(
        optimise_geometry=options.optimiseGeometry,
        embed_seed=options.embedSeed,
        rigid_macrocycles=options.rigidMacrocycles,
        flexible_amides=options.flexibleAmides,
        hydrate=options.hydrate,
        double_bond_penalty=options.doubleBondPenalty,
    )
