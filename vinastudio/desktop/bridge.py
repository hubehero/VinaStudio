"""QWebChannel bridge exposing native desktop capabilities to the web UI.

The web layer talks to the backend over HTTP/WebSocket for everything that is
data, and to this object for everything that must be native (file dialogs,
saving images, revealing paths). Every method returns JSON-safe primitives so
the JavaScript side stays trivial.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import platform
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from vinastudio.config import APP_VERSION, app_home, dev_server_url
from vinastudio.desktop.theme import DEFAULT_LANGUAGE, Language, t

log = logging.getLogger(__name__)

ALL_FILES_FILTER = "All files (*)"


class Bridge(QObject):
    """Object published on the ``vinastudio`` QWebChannel."""

    languageChanged = Signal(str)
    #: Emitted when the native menu asks the web layer to load a project file.
    projectOpenRequested = Signal(str)
    #: Emitted when the native menu asks the frontend to persist its state.
    projectSaveRequested = Signal(str)
    reloadRequested = Signal()
    devToolsRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._language: Language = DEFAULT_LANGUAGE

    # -- language ----------------------------------------------------------
    @Slot(result=str)
    def getLanguage(self) -> str:
        return self._language

    @Slot(str, result=bool)
    def setLanguage(self, language: str) -> bool:
        normalised: Language = "en" if language.lower().startswith("en") else "zh"
        if normalised == self._language:
            return False
        self._language = normalised
        self.languageChanged.emit(normalised)
        return True

    # -- app metadata ------------------------------------------------------
    @Slot(result=str)
    def appInfo(self) -> str:
        """Return version/platform/host details as a JSON object."""
        return json.dumps(
            {
                "name": "VinaStudio",
                "version": APP_VERSION,
                "platform": platform.system(),
                "platformRelease": platform.release(),
                "python": sys.version.split()[0],
                "home": str(app_home()),
                "development": dev_server_url() is not None,
                "language": self._language,
            }
        )

    # -- file dialogs ------------------------------------------------------
    @Slot(str, str, bool, result=str)
    def openFiles(self, title: str, filters: str, multiple: bool) -> str:
        """Show an open dialog; returns a JSON array of absolute paths."""
        dialog = QFileDialog(self._parent, title or "Open")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles if multiple else QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter(filters or ALL_FILES_FILTER)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return "[]"
        return json.dumps([str(p) for p in dialog.selectedFiles()])

    @Slot(str, str, result=str)
    def saveFile(self, title: str, suggested_name: str, filters: str) -> str:
        """Show a save dialog; returns the chosen absolute path or ``""``."""
        initial = str(Path(app_home()) / suggested_name) if suggested_name else str(app_home())
        path, _ = QFileDialog.getSaveFileName(
            self._parent, title or "Save", initial, filters or ALL_FILES_FILTER
        )
        return path or ""

    @Slot(str, result=str)
    def openDirectory(self, title: str) -> str:
        """Show a directory picker; returns the chosen absolute path or ``""``."""
        return QFileDialog.getExistingDirectory(self._parent, title or "Select folder") or ""

    # -- image / file output ----------------------------------------------
    @Slot(str, str, result=str)
    def saveImage(self, data_url: str, suggested_name: str) -> str:
        """Persist a ``data:image/png;base64,...`` payload chosen by the user."""
        path = self.saveFile("Save image", suggested_name or "view.png", "PNG image (*.png)")
        if not path:
            return ""
        if not Path(path).suffix:
            path += ".png"
        payload = data_url.split(",", 1)[-1]
        try:
            blob = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            self._error("Invalid image payload", str(exc))
            return ""
        try:
            Path(path).write_bytes(blob)
        except OSError as exc:
            self._error("Could not save image", str(exc))
            return ""
        return path

    @Slot(str, result=bool)
    def revealInFileManager(self, path: str) -> bool:
        """Open the containing folder of ``path`` in the system file manager."""
        target = Path(path)
        folder = target if target.is_dir() else target.parent
        if not folder.exists():
            return False
        if platform.system() == "Linux":
            try:
                subprocess.Popen(["xdg-open", str(folder)])
                return True
            except OSError:  # pragma: no cover - no xdg-open available
                pass
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # -- misc --------------------------------------------------------------
    @Slot()
    def quit(self) -> None:
        """Ask the desktop shell to close."""
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    @Slot(str, str)
    def notify(self, title: str, message: str) -> None:
        """Show a native information dialog."""
        QMessageBox.information(self._parent, title, message)

    @Slot(str)
    def requestReload(self, _reason: str = "") -> None:
        self.reloadRequested.emit()

    def windowTitle(self) -> str:
        return t("window.title", self._language)

    def _error(self, title: str, message: str) -> None:
        log.error("%s: %s", title, message)
        QMessageBox.warning(self._parent, title, message)
