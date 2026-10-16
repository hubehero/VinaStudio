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
# The build script always ``cd``s to the repository root before invoking
# PyInstaller, so ``os.getcwd()`` is the repo root.  The spec file lives
# at ``packaging/pyinstaller/vinastudio.spec`` relative to that root.
REPO_ROOT = Path(os.getcwd())
SPEC_ROOT = REPO_ROOT / "packaging" / "pyinstaller"
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

# No `vina` module exists on Windows — there is no wheel to install — so only ask
# PyInstaller for it where it can be imported. The packaged command-line backend
# covers that platform instead, which is the reason the Windows build works at all.
if sys.platform != "win32":
    hiddenimports.append("vina")

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

# Windows provides the Universal C Runtime and its API-set forwarders, and this
# application already requires Windows 10 1809 or newer
# (packaging/windows/vinastudio.iss). PyInstaller nevertheless collects the copies
# that extension wheels carry, and those copies land in `_internal` where they shadow
# the system ones — which is what makes the bootloader fail with
#     Failed to load Python DLL ...\_internal\python312.dll
#     LoadLibrary: Invalid access to memory location
# on a machine where the system runtime is present. The host Python loads that very
# file without complaint, so the file is not the problem; its neighbours are. Dropping
# them is safe on the supported Windows versions and is the difference between a
# bundle that starts and one that does not.
_SYSTEM_RUNTIME_PREFIXES = ("api-ms-win-", "ext-ms-win-")
_COLLISION_FILTERS = (
    # OpenSSL: `_ssl` needs the copy CPython was built against. rdkit ships its own,
    # and two files with one name means one of them silently wins — the loser's
    # consumer then fails with "Invalid access to memory location" while importing,
    # which is exactly how this bundle died on `_ssl` after the runtime DLLs were
    # sorted out. OpenSSL 3.x keeps a stable ABI, so keeping CPython's copy serves
    # both.
    ("libcrypto", "rdkit.libs"),
    ("libssl", "rdkit.libs"),
)
a.binaries = [
    entry
    for entry in a.binaries
    if not Path(entry[0]).name.lower().startswith(_SYSTEM_RUNTIME_PREFIXES)
    and Path(entry[0]).name.lower() != "ucrtbase.dll"
    and not any(
        Path(entry[0]).name.lower().startswith(name)
        and origin in str(entry[1]).replace("\\", "/")
        for name, origin in _COLLISION_FILTERS
    )
]

pyz = PYZ(a.pure)

#: A windowed build reports a fatal start-up problem in a message box, which nobody
#: can read on a build machine — and which keeps the process alive waiting for a
#: click. CI sets this to build the same bundle as a console application so the
#: bootloader's own words land in the log instead.
console_build = bool(os.environ.get("VINASTUDIO_CONSOLE_BUILD"))

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
    console=console_build,
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
    # Not the engine binary: UPX-compressed executables are a long-standing
    # antivirus false-positive trigger, and this one runs on students' Windows
    # machines. Its size (4 MB) is not worth that risk.
    upx_exclude=["vina", "vina.exe"],
    name="vinastudio",
)
