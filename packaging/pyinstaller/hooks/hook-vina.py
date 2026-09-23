"""PyInstaller hook for the ``vina`` package.

vina is a single C-extension module wrapping the AutoDock Vina docking engine
and its Boost dependencies.  The native library is the only binary; there are
no data files, but the Boost shared objects must travel alongside it.
"""

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# collect_all will pick up the .so / .pyd and any hidden imports.
vina_datas, vina_binaries, vina_hiddenimports = collect_all("vina")

# Fallback: ensure the Boost libraries that vina links against are bundled.
vina_binaries += collect_dynamic_libs("vina")

datas = vina_datas
binaries = vina_binaries
hiddenimports = vina_hiddenimports
