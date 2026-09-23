"""PyInstaller hook for the ``gemmi`` package.

gemmi is a C-extension wrapping Boost and the gemmi crystallography library.
The shared libraries it ships (and the Boost libs it links) must be bundled.
"""

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

gemmi_datas, gemmi_binaries, gemmi_hiddenimports = collect_all("gemmi")

# Extra safety: explicit scan for native libraries.
gemmi_binaries += collect_dynamic_libs("gemmi")

datas = gemmi_datas
binaries = gemmi_binaries
hiddenimports = gemmi_hiddenimports
