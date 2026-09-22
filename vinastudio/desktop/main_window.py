"""The native window that hosts the Vue interface inside a Chromium view."""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QFile, QIODevice, QSettings, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QMessageBox

from vinastudio.config import APP_NAME, app_home
from vinastudio.desktop.bridge import Bridge
from vinastudio.desktop.theme import DEFAULT_LANGUAGE, Language, app_icon, t

log = logging.getLogger(__name__)

#: JavaScript namespace the web application publishes for native menu actions.
JS_NAMESPACE = "window.vinastudio"


class MainWindow(QMainWindow):
    """Application shell: loaded interface, menus and the QWebChannel bridge."""

    def __init__(self, url: str, *, parent: Any = None) -> None:
        super().__init__(parent)
        self._url = url
        self._language: Language = DEFAULT_LANGUAGE
        self._settings = QSettings(
            str(app_home() / "settings.ini"), QSettings.Format.IniFormat
        )
        self._devtools_view: QWebEngineView | None = None
        self._devtools_page: QWebEnginePage | None = None
        self._profile: QWebEngineProfile | None = None

        self.setWindowTitle(t("window.title", self._language))
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1024, 680)

        self.bridge = Bridge(self)
        self.bridge.languageChanged.connect(self._on_language_changed)

        self._view = QWebEngineView(self)
        self._view.setPage(self._create_page())
        self._view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self._view)

        self._build_menus()
        self._install_web_channel()
        self._restore_geometry()
        self.statusBar().showMessage(t("status.ready", self._language))
        self._view.load(QUrl(url))

    # -- web view plumbing -------------------------------------------------
    def _create_page(self) -> QWebEnginePage:
        """Build a persistent profile so UI preferences survive restarts."""
        web_dir = app_home() / "webview"

        # The profile is deliberately unparented and held by the window, while
        # the page is parented to the profile. QtWebEngine then destroys the
        # page before the profile, which avoids the "Release of profile
        # requested but WebEnginePage still not deleted" warning on shutdown.
        profile = QWebEngineProfile(APP_NAME)
        self._profile = profile
        profile.setPersistentStoragePath(str(web_dir))
        profile.setCachePath(str(web_dir / "cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)

        page = QWebEnginePage(profile)
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        return page

    def _install_web_channel(self) -> None:
        """Expose ``bridge`` to the page and inject the Qt channel client."""
        channel = QWebChannel(self._view.page())
        channel.registerObject("bridge", self.bridge)
        self._view.page().setWebChannel(channel)

        source_file = QFile(":/qtwebchannel/qwebchannel.js")
        if not source_file.open(QIODevice.OpenModeFlag.ReadOnly):
            log.warning("qwebchannel.js unavailable; native bridge will stay disabled")
            return
        source = bytes(source_file.readAll().data()).decode("utf-8")
        source_file.close()

        script = QWebEngineScript()
        script.setName("qwebchannel-client")
        script.setSourceCode(source)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self._view.page().scripts().insert(script)

    @Slot(bool)
    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            self.statusBar().showMessage(t("status.ready", self._language))
            self._call_js("setLocale", self._language)
            return
        log.error("Failed to load %s", self._url)
        self._view.setHtml(_error_page(self._url, self._language))

    # -- native menus ------------------------------------------------------
    def _build_menus(self) -> None:
        language = self._language
        bar = self.menuBar()
        bar.clear()

        file_menu = bar.addMenu(t("menu.file", language))
        self._add_action(file_menu, "file.new", "Ctrl+N", lambda: self._call_js("newProject"))
        self._add_action(file_menu, "file.open", "Ctrl+O", lambda: self._call_js("openProject"))
        self._add_action(file_menu, "file.save", "Ctrl+S", lambda: self._call_js("saveProject"))
        self._add_action(
            file_menu, "file.save_as", "Ctrl+Shift+S", lambda: self._call_js("saveProjectAs")
        )
        file_menu.addSeparator()
        quit_action = self._add_action(file_menu, "file.quit", "Ctrl+Q", self.close)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)

        view_menu = bar.addMenu(t("menu.view", language))
        self._add_action(view_menu, "view.reload", "Ctrl+R", self._view.reload)
        self._add_action(view_menu, "view.devtools", "F12", self._open_devtools)
        view_menu.addSeparator()
        self._add_action(
            view_menu, "view.zoom_in", "Ctrl+=", lambda: self._zoom(1.1)
        )
        self._add_action(view_menu, "view.zoom_out", "Ctrl+-", lambda: self._zoom(1 / 1.1))
        self._add_action(
            view_menu, "view.zoom_reset", "Ctrl+0", lambda: self._view.setZoomFactor(1.0)
        )
        fullscreen = self._add_action(view_menu, "view.fullscreen", "F11", self._toggle_fullscreen)
        fullscreen.setCheckable(True)

        language_menu = bar.addMenu(t("menu.language", language))
        group = QActionGroup(self)
        group.setExclusive(True)
        for code, label in (("zh", "中文"), ("en", "English")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(code == self._language)
            action.triggered.connect(lambda _checked, c=code: self._request_locale(c))
            group.addAction(action)
            language_menu.addAction(action)

        help_menu = bar.addMenu(t("menu.help", language))
        self._add_action(help_menu, "help.shortcuts", "F1", self._show_shortcuts)
        self._add_action(help_menu, "help.cite", None, self._show_citation)
        help_menu.addSeparator()
        self._add_action(help_menu, "help.about", None, self._show_about)

    def _add_action(self, menu, key: str, shortcut: str | None, handler) -> QAction:  # type: ignore[no-untyped-def]
        action = QAction(t(key, self._language), self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    @Slot(str)
    def _on_language_changed(self, language: str) -> None:
        self._language = "en" if language.startswith("en") else "zh"
        self.setWindowTitle(t("window.title", self._language))
        self._build_menus()

    def _request_locale(self, code: str) -> None:
        """Ask the web layer to switch language; it reports back via the bridge."""
        self._call_js("setLocale", code)

    # -- actions -----------------------------------------------------------
    def _zoom(self, factor: float) -> None:
        self._view.setZoomFactor(max(0.4, min(3.0, self._view.zoomFactor() * factor)))

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _open_devtools(self) -> None:
        """Open the Chromium inspector in a separate native window."""
        if self._devtools_view is None:
            self._devtools_view = QWebEngineView()
            self._devtools_view.setWindowTitle("DevTools")
            self._devtools_page = QWebEnginePage(self._view.page().profile(), self)
            self._devtools_view.setPage(self._devtools_page)
            self._view.page().setDevToolsPage(self._devtools_page)
        self._devtools_view.resize(1080, 720)
        self._devtools_view.show()
        self._devtools_view.raise_()

    def _show_shortcuts(self) -> None:
        text = (
            "Ctrl+N 新建工程 / New project\n"
            "Ctrl+O 打开工程 / Open project\n"
            "Ctrl+S 保存工程 / Save project\n"
            "Ctrl+R 重新加载界面 / Reload interface\n"
            "F12 开发者工具 / Developer tools\n"
            "F11 全屏 / Full screen\n"
            "Ctrl+0 恢复缩放 / Reset zoom"
        )
        QMessageBox.information(self, t("help.shortcuts", self._language), text)

    def _show_citation(self) -> None:
        text = (
            "Trott, O., & Olson, A. J. (2010). AutoDock Vina: improving the speed and "
            "accuracy of docking with a new scoring function, efficient optimization, and "
            "multithreading. Journal of Computational Chemistry, 31(2), 455-461.\n\n"
            "Eberhardt, J., Santos-Martins, D., Tillack, A. F., & Forli, S. (2021). "
            "AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, and Python "
            "Bindings. Journal of Chemical Information and Modeling, 61(8), 3891-3898.\n\n"
            "Meeko: molecule parameterization and software interoperability for docking "
            "and beyond. Journal of Chemical Information and Modeling (2025)."
        )
        QMessageBox.information(self, t("help.cite", self._language), text)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            t("help.about", self._language),
            f"<b>{APP_NAME}</b> {self._version_text()}<br><br>"
            + t("about.text", self._language).replace("\n", "<br>"),
        )

    def _version_text(self) -> str:
        from vinastudio import __version__

        return __version__

    # -- geometry ----------------------------------------------------------
    def _restore_geometry(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)

    # -- helpers -----------------------------------------------------------
    def _call_js(self, function: str, *args: Any) -> None:
        """Invoke ``window.vinastudio.<function>(...)`` in the loaded page."""
        payload = ", ".join(json.dumps(arg) for arg in args)
        script = (
            f"(function(){{const ns={JS_NAMESPACE};"
            f"if(ns&&typeof ns.{function}==='function'){{ns.{function}({payload});}}}})();"
        )
        self._view.page().runJavaScript(script)

    @property
    def view(self) -> QWebEngineView:
        return self._view


def _error_page(url: str, language: Language) -> str:
    """Fallback page shown when the interface bundle cannot be loaded."""
    if language == "zh":
        heading = "界面资源未能加载"
        body = (
            "本地服务已启动，但前端构建产物缺失。请先构建界面："
            "<pre>uv run python scripts/build_web.py</pre>"
            "或使用开发模式运行：<pre>uv run python scripts/dev.py</pre>"
        )
    else:
        heading = "Interface bundle could not be loaded"
        body = (
            "The local service is running but the frontend build output is missing. "
            "Build the interface first:"
            "<pre>uv run python scripts/build_web.py</pre>"
            "Or run in development mode: <pre>uv run python scripts/dev.py</pre>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{APP_NAME}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         background:#0d1526; color:#e6edf7;
         font:15px/1.7 -apple-system,"Segoe UI","Noto Sans SC",sans-serif; }}
  .card {{ max-width:640px; padding:40px 44px; border-radius:16px;
          background:#151f36; border:1px solid #24314f; }}
  h1 {{ font-size:20px; margin:0 0 16px; color:#4fd1c5; }}
  pre {{ background:#0a1120; padding:10px 14px; border-radius:8px; overflow:auto;
        color:#9fd3ff; font-size:13px; }}
  code {{ color:#9fd3ff; }}
  .url {{ color:#8aa0c0; font-size:12px; margin-top:22px; word-break:break-all; }}
</style></head>
<body><div class="card">
  <h1>{heading}</h1>
  <p>{body}</p>
  <p class="url">{url}</p>
</div></body></html>"""
