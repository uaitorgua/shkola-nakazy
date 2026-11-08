"""Створення QApplication і запуск головного вікна."""

import sys

from PySide6.QtWidgets import QApplication

from .config import APP_NAME, ORG_NAME
from .logging_setup import setup_logging
from .ui.logo import app_icon
from .ui.main_window import MainWindow
from .ui.theme import STYLE


def main() -> int:
    setup_logging()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dsyao.skaner")   # власна іконка в панелі задач
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    args = [a for a in sys.argv[1:]]
    mode = next((a for a in args if a in ("--intertext", "--intertab")), None)
    files = [a for a in args if not a.startswith("--")]
    if mode is None and files and files[0].lower().endswith((".docx", ".html", ".htm", ".txt")):
        mode = "--intertext"
    elif mode is None and files and files[0].lower().endswith((".xlsx", ".csv")):
        mode = "--intertab"
    if mode == "--intertext":                      # субдодаток InterText окремо
        from pathlib import Path
        from .ui.editor_window import EditorWindow
        win = EditorWindow(None, "", "Документ")
        if files:
            win.load(Path(files[0]))
    elif mode == "--intertab":                     # субдодаток InterTab окремо
        from pathlib import Path
        from .ui.sheet_window import SheetWindow
        win = SheetWindow()
        if files:
            win.load(Path(files[0]))
    else:
        win = MainWindow()
    win.show()
    return app.exec()
