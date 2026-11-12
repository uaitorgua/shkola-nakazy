"""Обов'язкове оновлення: у фоні перевіряє сайт; якщо є новіша версія — модальне вікно
«Оновити зараз» / «Вийти». Працювати на старій версії не можна."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .. import __version__, updater


class _Check(QThread):
    found = Signal(dict)

    def run(self) -> None:
        info = updater.check()
        if info:
            self.found.emit(info)


class _Download(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, info: dict) -> None:
        super().__init__()
        self.info = info

    def run(self) -> None:
        try:
            self.done.emit(updater.download(self.info, lambda d, t: self.progress.emit(d, t)))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class UpdateChecker:
    def __init__(self, parent) -> None:
        self.parent = parent
        self._t = _Check()
        self._t.found.connect(self._ask)

    def start(self) -> None:
        self._t.start()

    def _ask(self, info: dict) -> None:
        store = updater.is_store_install()
        box = QMessageBox(self.parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Потрібне оновлення")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"Вийшла нова версія <b>{info['version']}</b> (у вас {__version__}).<br>"
                    "Щоб працювати далі, оновіть програму.<br>"
                    "Інсталятор завантажиться й запуститься автоматично.<br><br>"
                    f'Сайт програми: <a href="{updater.BASE}">{updater.BASE}</a>')
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        if store:
            box.setInformativeText("Програму встановлено з Microsoft Store — оновіть її там.")
        upd = box.addButton("Оновити зараз", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Вийти", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not upd:
            QApplication.quit()
            return
        if store:
            QDesktopServices.openUrl(QUrl(updater.STORE_URL))
            QApplication.quit()
            return
        self._download(info)

    def _download(self, info: dict) -> None:
        dlg = QProgressDialog("Завантаження оновлення…", None, 0, 100, self.parent)
        dlg.setWindowTitle("Оновлення")
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        self._d = _Download(info)
        self._d.progress.connect(lambda d, t: dlg.setValue(int(d * 100 / t)) if t else None)

        def ok(path: str) -> None:
            dlg.close()
            subprocess.Popen([path], close_fds=True)       # інсталятор закриє й замінить програму
            QApplication.quit()

        def fail(msg: str) -> None:
            dlg.close()
            QMessageBox.critical(self.parent, "Оновлення", f"Не вдалося завантажити оновлення:\n{msg}\n\n"
                                 f"Завантажте його вручну: {updater.BASE}")
            QDesktopServices.openUrl(QUrl(updater.BASE))
            QApplication.quit()

        self._d.done.connect(ok)
        self._d.failed.connect(fail)
        self._d.start()
        dlg.exec()
