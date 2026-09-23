"""PyInstaller hook for the ``meeko`` package.

meeko is a pure-Python toolkit for preparing AutoDock Vina input.
It has no native dependencies -- we just need to make sure all submodules are
found by the import machinery.
"""

from PyInstaller.utils.hooks import collect_all

meeko_datas, meeko_binaries, meeko_hiddenimports = collect_all("meeko")

datas = meeko_datas
binaries = meeko_binaries
hiddenimports = meeko_hiddenimports
