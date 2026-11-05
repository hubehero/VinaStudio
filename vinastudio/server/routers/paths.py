"""Allowed input paths at the API boundary (M8).

These endpoints accept files chosen by the native dialog, so they cannot be
fenced to the workspace. They can still refuse a path the parser would never
understand, and they must not echo the path back: an error message is otherwise
a boolean oracle over local files.
"""

from __future__ import annotations

from pathlib import Path

from vinastudio.core.chem.formats import LIGAND_SUFFIXES
from vinastudio.core.errors import InvalidInputError

#: The interaction parser reads these two layouts only.
RECEPTOR_PATH_SUFFIXES = frozenset({".pdb", ".pdbqt"})
#: ``parse_ligand_atoms`` currently reads SDF text and PDBQT.
LIGAND_PATH_SUFFIXES = frozenset({".sdf", ".pdbqt"})
#: RMSD/CSV references go through the shared RMSD reader.
REFERENCE_PATH_SUFFIXES = frozenset(LIGAND_SUFFIXES)


def require_file(value: str, suffixes: frozenset[str], kind: str) -> Path:
    """Resolve an input path that must exist and use a supported suffix."""
    try:
        path = Path(value)
        suffix = path.suffix.lower()
        is_file = path.is_file()
    except (OSError, ValueError):
        raise InvalidInputError(f"the selected {kind} file was not found") from None

    if suffix not in suffixes:
        raise InvalidInputError(
            f"the selected {kind} file has an unsupported format"
        )
    if not is_file:
        raise InvalidInputError(f"the selected {kind} file was not found")
    return path
