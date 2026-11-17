"""Вікно «Дані й копії»: резервні копії бази, збереження бази у файл, відновлення з копії або з файла.

Копії робляться й автоматично (backup.py): під час кожного запуску (30 останніх) і перед кожною зміною
будови бази при оновленні програми (не видаляються). Перед відновленням поточна база теж зберігається,
тож відновлення можна відкотити.
"""
from __future__ import annotations

import datetime as dt
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from .. import backup
from ..db import SCHEMA_VERSION


class DataDialog(QDialog):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.mw = main_window
        self.setWindowTitle("Дані й копії")
        self.resize(760, 520)
        info = QLabel("Усі накази, люди й налаштування зберігаються в одному файлі бази на цьому комп'ютері. "
                      "Програма сама робить копії: під час кожного запуску (30 останніх) і перед кожним "
                      "оновленням будови бази (ці не видаляються). Перед відновленням поточна база теж "
                      "зберігається.")
        info.setWordWrap(True)
        self.list = QTreeWidget(); self.list.setHeaderLabels(["Дата й час", "Коли зроблено", "Наказів"])
        self.list.setRootIsDecorated(False); self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(lambda *_: self.restore_selected())
        b1 = QHBoxLayout(); b2 = QHBoxLayout(); b3 = QHBoxLayout()
        for row, items in ((b1, (("Створити копію зараз", self.make_now), ("Відновити з вибраної копії",
                                                                            self.restore_selected),
                                 ("Відкрити теку з копіями", self.open_folder))),
                           (b2, (("Зберегти базу у файл…", self.export_file), ("Відновити з файла…", self.import_file))),
                           (b3, (("Експорт у JSON…", self.export_json), ("Імпорт з JSON…", self.import_json),
                                 ("Експорт у Excel…", self.export_xlsx)))):
            for text, slot in items:
                b = QPushButton(text); b.clicked.connect(slot); row.addWidget(b)
        self.path_lbl = QLabel(); self.path_lbl.setWordWrap(True); self.path_lbl.setStyleSheet("color:#666")
        self.path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(self.reject)
        v = QVBoxLayout(self)
        v.addWidget(info); v.addWidget(QLabel("<b>Резервні копії</b>")); v.addWidget(self.list, 1); v.addLayout(b1)
        v.addWidget(QLabel("<b>Перенесення на інший комп'ютер або зовнішній носій</b>")); v.addLayout(b2)
        v.addWidget(QLabel("<b>Формат, незалежний від версії програми</b> – JSON (повні дані, імпорт у будь-яку "
                           "новішу версію) і Excel (лише для перегляду й друку)")); v.addLayout(b3)
        v.addWidget(self.path_lbl); v.addWidget(close)
        self.load()

    @property
    def db(self):
        return self.mw.db

    def load(self):
        self.list.clear()
        for p in backup.list_backups(self.db.path):
            when, why = backup.describe(p)
            ok, _msg, n = backup.check_file(p, SCHEMA_VERSION)
            it = QTreeWidgetItem([when, why, str(n) if ok else "–"]); it.setData(0, Qt.UserRole, p)
            self.list.addTopLevelItem(it)
        for c in range(3):
            self.list.resizeColumnToContents(c)
        self.path_lbl.setText(f"Файл бази: {self.db.path}")

    def make_now(self):
        backup.make_backup(self.db.path, "manual")
        self.load()
        QMessageBox.information(self, "Дані й копії", "Копію створено.")

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(backup.backup_dir(self.db.path)))

    def export_file(self):
        name = f"Накази ШКОЛА {dt.date.today():%Y-%m-%d}.db"
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти базу у файл", name, "База «Накази ШКОЛА» (*.db)")
        if not path:
            return
        try:
            backup.export_to(self.db.con, path)
        except Exception as e:
            QMessageBox.warning(self, "Дані й копії", f"Не вдалося зберегти: {e}"); return
        QMessageBox.information(self, "Дані й копії", f"Базу збережено:\n{path}\n\nНа іншому комп'ютері: "
                                                      "«Дані й копії…» → «Відновити з файла…».")

    def export_json(self):
        from ..portable import export_json
        name = f"Накази ШКОЛА {dt.date.today():%Y-%m-%d}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Експорт у JSON", name, "JSON (*.json)")
        if not path:
            return
        try:
            counts = export_json(self.db, path)
        except Exception as e:
            QMessageBox.warning(self, "Дані й копії", f"Не вдалося: {e}"); return
        QMessageBox.information(self, "Дані й копії", f"Експортовано: наказів {counts.get('orders', 0)}, людей "
                                                      f"{counts.get('people', 0)}.\n{path}")

    def export_xlsx(self):
        from ..portable import export_xlsx
        name = f"Накази ШКОЛА {dt.date.today():%Y-%m-%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Експорт у Excel", name, "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_xlsx(self.db, path)
        except Exception as e:
            QMessageBox.warning(self, "Дані й копії", f"Не вдалося: {e}"); return
        QMessageBox.information(self, "Дані й копії", f"Збережено:\n{path}\n\nАркуші: накази, люди, графік "
                                                      "відпусток, додатки. Це файл для перегляду; для перенесення "
                                                      "даних використовуйте JSON.")

    def import_json(self):
        from ..portable import ImportError_, import_json
        path, _ = QFileDialog.getOpenFileName(self, "Імпорт з JSON", "", "JSON (*.json)")
        if not path:
            return
        tmp = os.path.join(os.path.dirname(self.db.path), f"import-{dt.datetime.now():%Y%m%d-%H%M%S}.db")
        try:
            rep = import_json(path, tmp)
        except ImportError_ as e:
            QMessageBox.warning(self, "Дані й копії", str(e)); return
        except Exception as e:
            QMessageBox.warning(self, "Дані й копії", f"Не вдалося прочитати дані: {e}"); return
        try:
            skipped = "".join(f"\n– {t}: {', '.join(c)}" for t, c in rep["skipped"].items())
            msg = (f"Наказів: {rep['rows'].get('orders', 0)}, людей: {rep['rows'].get('people', 0)}"
                   + (f" (експорт версії {rep['from_version']})" if rep.get("from_version") else "") + "."
                   + (f"\nНе перенесено (у цій версії таких полів немає):{skipped}" if skipped else ""))
            if QMessageBox.question(self, "Імпорт з JSON", f"Замінити поточну базу даними з файла?\n{msg}\n\n"
                                    "Поточну базу програма спершу збереже копією «перед відновленням».") \
                    != QMessageBox.Yes:
                return
            self.mw.replace_db(tmp)
            self.load()
            QMessageBox.information(self, "Дані й копії", "Дані імпортовано.")
        finally:
            for ext in ("", "-wal", "-shm"):
                if os.path.exists(tmp + ext):
                    os.remove(tmp + ext)

    def restore_selected(self):
        it = self.list.currentItem()
        if it:
            self._restore(it.data(0, Qt.UserRole), f"копії від {it.text(0)}")

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Відновити з файла", "", "База «Накази ШКОЛА» (*.db)")
        if path:
            self._restore(path, f"файла {os.path.basename(path)}")

    def _restore(self, path: str, what: str):
        ok, msg, n = backup.check_file(path, SCHEMA_VERSION)
        if not ok:
            QMessageBox.warning(self, "Дані й копії", msg); return
        if QMessageBox.question(
                self, "Відновлення", f"Замінити поточну базу даними з {what}?\n{msg}\n\nПоточну базу програма "
                "спершу збереже копією «перед відновленням», тож її можна буде повернути.") != QMessageBox.Yes:
            return
        try:
            self.mw.replace_db(path)
        except Exception as e:
            QMessageBox.warning(self, "Дані й копії", f"Не вдалося відновити: {e}"); return
        self.load()
        QMessageBox.information(self, "Дані й копії", "Базу відновлено.")
