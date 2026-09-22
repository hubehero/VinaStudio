"""Central configuration: filesystem layout, defaults and constants.

This module must stay free of Qt and FastAPI imports so that ``core`` and
``tests`` can import it cheaply.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

APP_NAME: Final = "VinaStudio"
APP_ID: Final = "vinastudio"
APP_VERSION: Final = "0.1.0"

PACKAGE_DIR: Final = Path(__file__).resolve().parent
STATIC_DIR: Final = PACKAGE_DIR / "server" / "static"
RESOURCES_DIR: Final = PACKAGE_DIR / "resources"
SAMPLE_DIR: Final = RESOURCES_DIR / "sample"

#: Environment variable pointing the desktop shell at a Vite dev server.
DEV_SERVER_ENV: Final = "VINASTUDIO_DEV_SERVER_URL"
DEV_SERVER_DEFAULT: Final = "http://127.0.0.1:5173"

#: Environment variable overriding the writable application home.
HOME_ENV: Final = "VINASTUDIO_HOME"
HOME_DEFAULT_NAME: Final = ".vinastudio"

#: The local API server only ever binds to loopback.
HOST: Final = "127.0.0.1"

ScoringFunction = Literal["vina", "vinardo", "ad4"]

#: Number of tunable weights per scoring function (``Vina.set_weights`` contract).
SCORING_WEIGHT_COUNT: Final[dict[str, int]] = {"vina": 7, "vinardo": 6, "ad4": 6}

#: Scoring functions that can compute their affinity maps natively.
NATIVE_MAP_SCORING: Final[frozenset[str]] = frozenset({"vina", "vinardo"})

#: Ligand input formats accepted by the preparation pipeline.
LIGAND_INPUT_SUFFIXES: Final[tuple[str, ...]] = (".mol", ".sdf", ".mol2", ".pdb")

#: Receptor input formats accepted by the preparation pipeline.
RECEPTOR_INPUT_SUFFIXES: Final[tuple[str, ...]] = (".pdb", ".cif", ".mmcif", ".ent")

#: Vina grid spacing default (Angstrom).
DEFAULT_SPACING: Final = 0.375

#: Default maximum upload size in megabytes.
#: Covers virtually all molecular files while preventing abuse.
#: PDB: 100KB-10MB, SDF: 10KB-5MB, mmCIF: up to 100MB for large complexes.
DEFAULT_MAX_UPLOAD_MB: Final = 100

#: Environment variable to override the upload limit.
UPLOAD_LIMIT_ENV: Final = "VINASTUDIO_MAX_UPLOAD_MB"


def app_home() -> Path:
    """Return (and create) the writable per-user application directory."""
    root = Path(os.environ.get(HOME_ENV) or (Path.home() / HOME_DEFAULT_NAME)).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def jobs_dir() -> Path:
    """Directory holding one isolated folder per docking job."""
    path = app_home() / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    """Directory for derived artefacts (converted SDF, cubes, surfaces)."""
    path = app_home() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def projects_dir() -> Path:
    """Default location offered when saving a ``.vinaproj`` project."""
    path = app_home() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """Directory for application and docking logs."""
    path = app_home() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dev_server_url() -> str | None:
    """Return the Vite dev server URL when running in development mode."""
    return os.environ.get(DEV_SERVER_ENV) or None


def max_upload_bytes() -> int:
    """Return the maximum upload size in bytes, configurable via environment."""
    try:
        mb = int(os.environ.get(UPLOAD_LIMIT_ENV, DEFAULT_MAX_UPLOAD_MB))
        return mb * 1024 * 1024
    except (ValueError, TypeError):
        return DEFAULT_MAX_UPLOAD_MB * 1024 * 1024


@dataclass(slots=True)
class DockingDefaults:
    """Default docking parameters surfaced in the UI.

    Values mirror the AutoDock Vina defaults so that the application behaves
    like the reference command-line tool out of the box.
    """

    scoring: ScoringFunction = "vina"
    cpu: int = 0  # 0 => use every available core
    seed: int = 0  # 0 => pick a random seed
    no_refine: bool = False
    verbosity: int = 1
    exhaustiveness: int = 8
    n_poses: int = 20
    min_rmsd: float = 1.0
    max_evals: int = 0  # 0 => heuristic
    energy_range: float = 3.0
    spacing: float = DEFAULT_SPACING
    force_even_voxels: bool = False
    box_size: tuple[float, float, float] = field(default_factory=lambda: (20.0, 20.0, 20.0))
    autobox_extend: float = 0.0


DEFAULTS: Final = DockingDefaults()
