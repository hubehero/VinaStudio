"""Qt / Chromium environment preparation.

Must run **before** ``PySide6.QtWebEngineWidgets`` is imported, which is why it
lives in its own module rather than in ``main_window``.
"""

from __future__ import annotations

import os


def prepare_qt_environment() -> None:
    """Apply the environment tweaks QtWebEngine needs on Linux desktops."""
    flags: list[str] = []

    # Chromium refuses to start its sandbox when running as root (containers,
    # CI, some distro setups). Fall back to --no-sandbox only in that case, or
    # when the user explicitly asks for it.
    if _needs_no_sandbox():
        flags.append("--no-sandbox")

    # Software rendering keeps the app usable on machines without a working GPU
    # stack. Opt-in rather than default, since GPU rendering is much faster.
    if os.environ.get("VINASTUDIO_SOFTWARE_RENDER") == "1":
        flags.append("--disable-gpu")

    if flags:
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([existing, *flags]).strip()


def _needs_no_sandbox() -> bool:
    override = os.environ.get("VINASTUDIO_NO_SANDBOX")
    if override == "1":
        return True
    if override == "0":
        return False
    try:
        return os.geteuid() == 0
    except AttributeError:  # pragma: no cover - non-POSIX platform
        return False
