"""Docking backends: one contract, two ways to reach Vina.

``core.docking.run_docking`` drives the Python API (in-process, the default) and
``engines.vina_cli.run_docking_cli`` drives the official command-line binary —
the same 1.2.7 engine, reachable on platforms whose ``vina`` has no Python
module. Both take a ``DockingParams`` and return a ``DockingResult``.

``common.py`` holds the parts that must not diverge between them: the parser for
Vina's stdout. Two copies of that would drift, and a drift there makes the
progress bar lie.
"""
