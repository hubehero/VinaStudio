"""Application entry point: start the local API server, then the Qt window."""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import sys

from vinastudio import __version__
from vinastudio.config import APP_NAME, dev_server_url
from vinastudio.desktop.server_thread import LocalServer
from vinastudio.logging_setup import setup_logging

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vinastudio", description=__doc__)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument(
        "--ui-url",
        default=None,
        help="Load the interface from this URL instead of the bundled build.",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=0,
        help="Port for the loopback API server (0 picks a free port).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Guard: when PyInstaller --onedir spawns child processes via
    # multiprocessing.get_context("spawn"), they re-execute this entry point.
    # Child processes must not initialise Qt or start the API server.
    if multiprocessing.parent_process() is not None:
        return 0

    args = _parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    # Order matters: the Chromium environment must be configured before any
    # QtWebEngine module is imported.
    from vinastudio.desktop.env import prepare_qt_environment

    prepare_qt_environment()

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    # QtWebEngine requires shared OpenGL contexts; this must precede QApplication.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication(sys.argv[:1])
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(__version__)
    application.setOrganizationName(APP_NAME)

    from vinastudio.desktop.theme import app_icon
    from vinastudio.server.app import create_app

    application.setWindowIcon(app_icon())

    server = LocalServer(create_app(), port=args.api_port)
    try:
        server.start()
    except Exception:
        log.exception("Unable to start the local API server")
        return 1

    url = args.ui_url or dev_server_url() or server.base_url
    log.info("Loading interface from %s", url)

    from vinastudio.desktop.main_window import MainWindow

    window = MainWindow(url)
    window.show()

    try:
        return application.exec()
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
