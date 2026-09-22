"""Chrome for the native window: icon, palette and bilingual menu strings."""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

from vinastudio.config import APP_NAME

Language = Literal["zh", "en"]

DEFAULT_LANGUAGE: Final[Language] = "zh"

ASSETS_DIR: Final = Path(__file__).resolve().parent / "assets"
ICON_PATH: Final = ASSETS_DIR / "icon.svg"

#: Native window chrome. The web layer has its own vue-i18n catalogue.
STRINGS: Final[dict[str, dict[Language, str]]] = {
    "window.title": {"zh": f"{APP_NAME} — 分子对接工作台", "en": f"{APP_NAME} — Docking Workbench"},
    "menu.file": {"zh": "文件", "en": "File"},
    "file.new": {"zh": "新建工程", "en": "New Project"},
    "file.open": {"zh": "打开工程…", "en": "Open Project…"},
    "file.save": {"zh": "保存工程", "en": "Save Project"},
    "file.save_as": {"zh": "工程另存为…", "en": "Save Project As…"},
    "file.quit": {"zh": "退出", "en": "Quit"},
    "menu.view": {"zh": "视图", "en": "View"},
    "view.reload": {"zh": "重新加载界面", "en": "Reload Interface"},
    "view.devtools": {"zh": "开发者工具", "en": "Developer Tools"},
    "view.zoom_in": {"zh": "放大", "en": "Zoom In"},
    "view.zoom_out": {"zh": "缩小", "en": "Zoom Out"},
    "view.zoom_reset": {"zh": "恢复缩放", "en": "Reset Zoom"},
    "view.fullscreen": {"zh": "全屏", "en": "Full Screen"},
    "menu.language": {"zh": "语言", "en": "Language"},
    "menu.help": {"zh": "帮助", "en": "Help"},
    "help.shortcuts": {"zh": "快捷键", "en": "Shortcuts"},
    "help.cite": {"zh": "引用 AutoDock Vina", "en": "Cite AutoDock Vina"},
    "help.homepage": {"zh": "项目主页", "en": "Project Homepage"},
    "help.about": {"zh": "关于", "en": "About"},
    "status.ready": {"zh": "就绪", "en": "Ready"},
    "status.server": {"zh": "本地服务", "en": "Local service"},
    "about.text": {
        "zh": (
            "以 AutoDock Vina 为对接引擎，Meeko 负责分子参数化与格式转换，"
            "界面由 Vue 3 + 3Dmol.js 构建并内嵌于 PySide6。\n\n"
            "打分函数：Vina / Vinardo / AutoDock4"
        ),
        "en": (
            "Docking engine: AutoDock Vina. Molecular parameterisation and format "
            "conversion: Meeko. Interface built with Vue 3 + 3Dmol.js, embedded in PySide6.\n\n"
            "Scoring functions: Vina / Vinardo / AutoDock4"
        ),
    },
}


def t(key: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """Translate a native chrome string."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(language, entry[DEFAULT_LANGUAGE])


def app_icon():  # type: ignore[no-untyped-def]
    """Load the application icon (returns ``None`` when the asset is missing)."""
    from PySide6.QtGui import QIcon

    if not ICON_PATH.exists():
        return QIcon()
    return QIcon(str(ICON_PATH))
