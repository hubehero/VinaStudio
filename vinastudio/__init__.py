"""VinaStudio — a modern desktop workbench for AutoDock Vina docking."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vinastudio")
except PackageNotFoundError:
    # Editable install or running from source without packaging metadata.
    __version__ = "0.0.0"

__all__ = ["__version__"]
