"""PyInstaller hook for PySide6 QtWebEngine.

Ensures the Chromium-based ``QtWebEngineProcess`` binary and its resource
files (icudtl.dat, qtwebengine_resources.pak, locales/) are collected into
the bundle.  Without these the embedded QWebEngineView crashes on launch.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

# ---- Collect everything from the two QtWebEngine packages ----
we_core_datas, we_core_bins, we_core_hiddens = collect_all(
    "PySide6.QtWebEngineCore"
)
we_widgets_datas, we_widgets_bins, we_widgets_hiddens = collect_all(
    "PySide6.QtWebEngineWidgets"
)

datas = we_core_datas + we_widgets_datas
binaries = we_core_bins + we_widgets_bins
hiddenimports = we_core_hiddens + we_widgets_hiddens

# ---- Locate QtWebEngineProcess and its resources ----
try:
    import PySide6
    pyside6_dir = Path(PySide6.__file__).parent
except ImportError:
    pyside6_dir = None

if pyside6_dir is not None:
    # QtWebEngineProcess binary lives in Qt/libexec/ or Qt/bin/ depending on
    # platform and PySide6 wheel layout.
    for search_dir in [
        pyside6_dir / "Qt" / "libexec",
        pyside6_dir / "Qt" / "bin",
        pyside6_dir / "Qt" / "lib",
    ]:
        proc = search_dir / "QtWebEngineProcess"
        if proc.exists():
            binaries.append((str(proc), str(Path("Qt") / "libexec")))
            break

    # ICU data, Chromium resource packs, and locale files.
    for res_subdir in [
        "Qt" / "resources",
        "Qt" / "lib" / "QtWebEngineProcess.app" / "Contents" / "Resources",
    ]:
        res_dir = pyside6_dir / res_subdir
        if res_dir.is_dir():
            for fname in [
                "icudtl.dat",
                "qtwebengine_resources.pak",
                "qtwebengine_resources_100p.pak",
                "qtwebengine_resources_200p.pak",
            ]:
                fpath = res_dir / fname
                if fpath.exists():
                    datas.append((str(fpath), str(res_subdir)))

            # Locales directory
            locales_dir = res_dir / "qtwebengine_locales"
            if locales_dir.is_dir():
                datas.append((str(locales_dir), str(res_subdir / "qtwebengine_locales")))

            # Snapshot blobs (required on some Qt versions)
            for fname in ["snapshot_blob.bin", "v8_context_snapshot.bin"]:
                fpath = res_dir / fname
                if fpath.exists():
                    datas.append((str(fpath), str(res_subdir)))
