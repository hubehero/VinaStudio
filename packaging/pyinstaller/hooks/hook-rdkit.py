"""PyInstaller hook for rdkit.

rdkit ships a large tree of shared libraries, data files (e.g. base features,
SMARTS patterns, parameter files) and submodules.  ``collect_all`` catches the
bulk of it; we additionally ensure ``rdkit.Chem`` data files are included
because some are discovered via ``pkg_resources`` at runtime.
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

# Full recursive collect: binaries, data, and hidden-imports.
rdkit_datas, rdkit_binaries, rdkit_hiddenimports = collect_all("rdkit")

# rdkit.Chem carries extra data (e.g. MinimalLib patterns) that may be loaded
# through ``importlib.resources`` or ``pkg_resources``.
chem_data = collect_data_files("rdkit.Chem", include_py_files=True)

datas = rdkit_datas + chem_data
binaries = rdkit_binaries
hiddenimports = rdkit_hiddenimports
