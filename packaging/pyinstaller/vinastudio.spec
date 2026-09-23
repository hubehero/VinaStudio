# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for VinaStudio --onedir build.

Usage (from the repo root):
    cd vina_simple
    pyinstaller packaging/pyinstaller/vinastudio.spec

All custom hooks live in packaging/pyinstaller/hooks/ and are referenced
via ``hookspath`` below so PyFinder picks them up automatically.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# ``SPECDIR`` is set by PyInstaller when running a .spec file via the CLI.
# When invoked via ``pyinstaller path/to/spec``, ``sys.argv[1]`` is the spec
# path and ``os.path`` resolves it reliably even if ``SPECDIR`` is absent.
_spec_candidate = os.path.join(os.getcwd(), sys.argv[-1]) if len(sys.argv) > 1 else "."
SPEC_ROOT = Path(_spec_candidate).resolve().parent
# The repository root (two levels up from the spec file).
REPO_ROOT = SPEC_ROOT.parent.parent
# The vinastudio package directory.
VINASTUDIO_PKG = REPO_ROOT / "vinastudio"

# ---------------------------------------------------------------------------
# Data files (source -> destination inside the bundle)
# ---------------------------------------------------------------------------
datas = [
    # Built Vue 3 frontend SPA
    (str(VINASTUDIO_PKG / "server" / "static"), str(Path("vinastudio") / "server" / "static")),
    # Sample & validation data
    (str(VINASTUDIO_PKG / "resources"), str(Path("vinastudio") / "resources")),
    # Desktop assets (icon.svg, etc.)
    (str(VINASTUDIO_PKG / "desktop" / "assets"), str(Path("vinastudio") / "desktop" / "assets")),
]

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
# Some packages use lazy / plugin-style imports that PyInstaller's static
# analysis misses.  We enumerate the most important ones here; the rest is
# handled by the custom hooks under ``hooks/``.
hiddenimports = [
    # --- QtWebEngine ---
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",

    # --- Scientific Python ---
    "rdkit",
    "rdkit.Chem",
    "rdkit.Chem.AllChem",
    "rdkit.Chem.rdMolDescriptors",
    "rdkit.Chem.rdMolAlign",
    "rdkit.Chem.Draw",
    "rdkit.Chem.inchi",
    "rdkit.Chem.rdmolfiles",
    "rdkit.Chem.rdmolops",
    "rdkit.Chem.rdchem",
    "rdkit.Chem.Descriptors",
    "rdkit.Chem.MACCSkeys",
    "rdkit.Chem.AtomPairs",
    "rdkit.Chem.Fingerprints",
    "rdkit.Chem.PandasTools",
    "rdkit.Chem.Templates",
    "rdkit.Chem.EState",
    "rdkit.Chem.Lipinski",
    "rdkit.Chem.GraphDescriptors",
    "rdkit.Chem.rdFreeSASA",
    "rdkit.Chem.MolStandardize",
    "rdkit.DataStructs",
    "rdkit.Geometry",
    "rdkit.RDLogger",
    "rdkit.RDBase",

    "meeko",
    "meeko.molsetup",
    "meeko.writer",
    "meeko.preparation",
    "meeko.gridset",

    "vina",

    "gemmi",

    # --- FastAPI / Uvicorn ---
    "uvicorn",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.config",
    "uvicorn.main",
    "fastapi",
    "fastapi.responses",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "starlette",
    "starlette.routing",
    "starlette.responses",
    "starlette.staticfiles",
    "starlette.websockets",
    "multipart",
    "python_multipart",

    # --- Multiprocessing (spawn context is critical for --onedir) ---
    "multiprocessing",
    "multiprocessing.spawn",
    "multiprocessing.popen_spawn_posix",

    # --- Misc ---
    "json",
]

# ---------------------------------------------------------------------------
# Collect sub-packages
# ---------------------------------------------------------------------------
# PySide6 ships dozens of subpackages that contain Qt plugins, translations,
# and resource files.  ``collect_all`` is the safest way to gather them.
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_dynamic_libs

pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all("PySide6")

# Collect QtWebEngine separately (large, separate wheel on some platforms).
qtwe_datas, qtwe_binaries, qtwe_hiddenimports = collect_all("PySide6.QtWebEngineCore")
qtwe_datas2, qtwe_binaries2, qtwe_hiddenimports2 = collect_all("PySide6.QtWebEngineWidgets")

datas += pyside6_datas + qtwe_datas + qtwe_datas2
binaries = pyside6_binaries + qtwe_binaries + qtwe_binaries2
hiddenimports += pyside6_hiddenimports + qtwe_hiddenimports + qtwe_hiddenimports2

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(REPO_ROOT / "vinastudio" / "__main__.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(SPEC_ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Tk / matplotlib backends not needed in the GUI shell
        "tkinter",
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
        "ruff",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vinastudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # On Windows use the generated .ico; on Linux the .desktop file provides the icon.
    icon=str(SPEC_ROOT.parent / "windows" / "icon.ico")
    if sys.platform == "win32" and (SPEC_ROOT.parent / "windows" / "icon.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="vinastudio",
)
