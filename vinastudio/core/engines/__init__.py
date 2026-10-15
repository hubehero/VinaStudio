"""Docking backends: one contract, two ways to reach Vina.

``core.docking.run_docking`` drives the Python API (in-process, the default) and
``engines.vina_cli.run_docking_cli`` drives the official command-line binary —
the same 1.2.7 engine, reachable on platforms whose ``vina`` has no Python
module. Both take a ``DockingParams`` and return a ``DockingResult``; callers do
not choose between them, they ask :func:`resolve_backend` what this machine can
run.

``common.py`` holds the parts that must not diverge: the parser for Vina's stdout.
"""

from __future__ import annotations

import importlib.util
import os

#: ``DockingParams.engine`` values. ``"vina"`` is the Python API, ``"vina-cli"``
#: the binary; a future GPU engine would be another name here.
API_BACKEND = "vina"
CLI_BACKEND = "vina-cli"

#: Force a door for a whole machine (support, and testing the fallback):
#: ``auto`` (default), ``api`` or ``cli``.
ENV_BACKEND = "VINASTUDIO_VINA_BACKEND"

_ENV_CHOICES = {"", "auto", "api", "cli"}


def api_available() -> bool:
    """Whether the ``vina`` Python module can be imported on this machine."""
    return importlib.util.find_spec("vina") is not None


def cli_available() -> bool:
    """Whether the command-line binary has been fetched."""
    from vinastudio.core.engines.vina_cli import cli_path

    try:
        cli_path()
    except FileNotFoundError:
        return False
    return True


def resolve_backend(engine: str | None = None) -> str:
    """Which backend a run should use.

    Precedence, most explicit first:

    1. ``engine``: ``"vina-cli"`` asks for the binary; ``"vina"`` (and empty)
       name the *engine* and leave the door to the machine — the default has to
       mean that, or the fallback below would never run on Windows.
    2. ``VINASTUDIO_VINA_BACKEND`` (``api`` / ``cli``): an operator forcing one
       door for a whole machine, which is also how the fallback gets tested.
    3. What this machine can run: the Python API when its module imports, the
       binary when it does not — exactly the Windows situation.

    Nothing is guessed. If neither is usable the error names both; an engine we
    do not implement (``"unidock"``) stays an error rather than quietly docking
    with a different one.
    """
    if engine and engine not in {API_BACKEND, CLI_BACKEND}:
        raise ValueError(f"unknown docking engine: {engine!r}")
    if engine == CLI_BACKEND:
        return CLI_BACKEND

    override = os.environ.get(ENV_BACKEND, "").strip().lower()
    if override not in _ENV_CHOICES:
        raise ValueError(f"{ENV_BACKEND} must be auto, api or cli — got {override!r}")
    if override == "api":
        return API_BACKEND
    if override == "cli":
        return CLI_BACKEND

    if api_available():
        return API_BACKEND
    if cli_available():
        return CLI_BACKEND
    raise RuntimeError(
        "no docking backend is usable: the `vina` Python module is not installed "
        "and no command-line binary was found — run "
        "`uv run python scripts/fetch_vina_cli.py`"
    )


def backend_report() -> dict[str, object]:
    """What ``/api/system/info`` shows: the door this machine would use, and why.

    Honest about the difference: the two backends share the engine but not the
    packaging, so "which one am I running" is a question worth answering when a
    run behaves unexpectedly.
    """
    api_here = api_available()
    cli_here = cli_available()
    override = os.environ.get(ENV_BACKEND, "").strip().lower()
    report: dict[str, object] = {
        "apiAvailable": api_here,
        "cliAvailable": cli_here,
        "override": override or "auto",
    }
    try:
        backend = resolve_backend()
    except (ValueError, RuntimeError) as exc:
        report["backend"] = None
        report["reason"] = str(exc)
        report["reasonCode"] = "unavailable"
        return report

    report["backend"] = backend
    if override == "cli" and backend == CLI_BACKEND:
        report["reason"] = f"forced by {ENV_BACKEND}=cli"
        report["reasonCode"] = "forced-cli"
    elif override == "api" and backend == API_BACKEND:
        report["reason"] = f"forced by {ENV_BACKEND}=api"
        report["reasonCode"] = "forced-api"
    elif backend == API_BACKEND:
        report["reason"] = "the vina Python module is installed"
        report["reasonCode"] = "module-installed"
    else:
        report["reason"] = "the vina Python module is missing, so the binary is used"
        report["reasonCode"] = "module-missing"
    return report
