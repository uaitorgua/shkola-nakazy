"""Обов'язкове оновлення через Microsoft Store: у фоні звіряє версію з каталогом Store;
якщо є новіша — модальне вікно «Оновити в Microsoft Store» / «Вийти». Працювати на старій версії не можна."""
from __future__ import annotations

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import __version__, updater


class _Check(QThread):
    found = Signal(dict)

    def run(self) -> None:
        info = updater.check()
        if info:
            self.found.emit(info)


class UpdateChecker:
    def __init__(self, parent) -> None:
        self.parent = parent
        self._t = _Check()
        self._t.found.connect(self._ask)

    def start(self) -> None:
        self._t.start()

    def _ask(self, info: dict) -> None:
        box = QMessageBox(self.parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Потрібне оновлення")
        box.setTextFormat(Qt.TextFormat.RichText)
        how = ("Натисніть «Оновити» на сторінці програми в Microsoft Store." if updater.is_store_install()
               else "Встановіть програму з Microsoft Store — далі вона оновлюватиметься сама.")
        box.setText(f"Вийшла нова версія <b>{info['version']}</b> (у вас {__version__}).<br>"
                    f"Щоб працювати далі, оновіть програму.<br>{how}<br><br>"
                    f'Microsoft Store: <a href="{updater.WEB_URL}">{updater.WEB_URL}</a>')
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        upd = box.addButton("Оновити в Microsoft Store", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Вийти", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is upd and not QDesktopServices.openUrl(QUrl(updater.STORE_URL)):
            QDesktopServices.openUrl(QUrl(updater.WEB_URL))
        QApplication.quit()
