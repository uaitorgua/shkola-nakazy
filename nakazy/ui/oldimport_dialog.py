"""Майстер імпорту архівних наказів: файли або тека → таблиця розпізнаного → виправлення → запис."""
from __future__ import annotations

import os

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QSpinBox, QSplitter, QTableWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .. import oldimport
from ..db import KINDS, Database, RegistrationError

COLS = ["Файл", "Вид", "№", "Дата", "Заголовок", "Підписав", "Перевірити"]
WARN = QColor("#fff1d6")


class OldImportDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.items: list[oldimport.Parsed] = []
        self.setWindowTitle("Імпорт наявних наказів (DOCX, DOC, PDF, скани)")
        self.resize(1300, 760)
        top = QHBoxLayout()
        for text, slot in (("Додати файли…", self.add_files), ("Додати теку…", self.add_folder)):
            b = QPushButton(text); b.clicked.connect(slot); top.addWidget(b)
        top.addWidget(QLabel("Жовтим позначено те, що треба перевірити. Клітинки можна виправляти."))
        top.addStretch()
        self.table = QTableWidget(0, len(COLS)); self.table.setHorizontalHeaderLabels(COLS)
        self.table.setColumnWidth(0, 160); self.table.setColumnWidth(1, 190); self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 120); self.table.setColumnWidth(4, 420); self.table.setColumnWidth(5, 150)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda r, *_: self.show_text(r))
        self.text = QTextEdit()
        self.text.setPlaceholderText("Текст вибраного наказу (можна виправити нерозпізнане перед записом)")
        self.text.textChanged.connect(self._text_changed)
        sp = QSplitter(); sp.addWidget(self.table); sp.addWidget(self.text); sp.setSizes([900, 400])
        bottom = QHBoxLayout()
        rm = QPushButton("Прибрати рядок"); rm.clicked.connect(self.remove_row)
        self.ok = QPushButton("Записати в базу"); self.ok.clicked.connect(self.apply)
        bottom.addWidget(rm); bottom.addStretch(); bottom.addWidget(self.ok)
        v = QVBoxLayout(self); v.addLayout(top); v.addWidget(sp, 1); v.addLayout(bottom)
        self._cur = -1

    # додавання
    def add_files(self):
        flt = "Накази (" + " ".join("*" + e for e in oldimport.SUPPORTED) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Накази", "", flt)
        self.load(paths)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Тека з наказами")
        if d:
            self.load(oldimport.scan_folder(d))

    def load(self, paths: list[str]):
        if not paths:
            return
        prog = QProgressDialog("Читаю накази…", "Зупинити", 0, len(paths), self)
        prog.setWindowModality(Qt.WindowModal)
        for i, p in enumerate(paths):
            prog.setValue(i); prog.setLabelText(os.path.basename(p)); QApplication.processEvents()
            if prog.wasCanceled():
                break
            self.items.append(oldimport.parse_file(p)); self._add_row(self.items[-1])
        prog.setValue(len(paths))

    def _add_row(self, p: oldimport.Parsed):
        r = self.table.rowCount(); self.table.insertRow(r)
        name = QLineEdit(os.path.basename(p.path)); name.setReadOnly(True)
        kind = QComboBox()
        for k in KINDS:
            kind.addItem(k.title + (f" (-{k.suffix})" if k.suffix else ""), k.code)
        kind.setCurrentIndex(kind.findData(p.kind))
        num = QSpinBox(); num.setRange(0, 9999); num.setValue(p.number or 0)
        date = QDateEdit(); date.setDisplayFormat("dd.MM.yyyy"); date.setCalendarPopup(True)
        date.setDate(QDate.fromString(p.date, "yyyy-MM-dd") if p.date else QDate(2000, 1, 1))
        title = QLineEdit(p.title); signer = QLineEdit(p.signer)
        probs = QLineEdit("; ".join(oldimport.problems(p))); probs.setReadOnly(True)
        for c, w in enumerate((name, kind, num, date, title, signer, probs)):
            self.table.setCellWidget(r, c, w)
        sure = p.sure
        for c, ok in ((1, sure.get("kind")), (2, p.number and sure.get("number")), (3, p.date and sure.get("date")),
                      (4, bool(p.title))):
            if not ok:
                self.table.cellWidget(r, c).setStyleSheet("background:#fff1d6")
        if p.error:
            probs.setStyleSheet("background:#ffd6d6")

    def show_text(self, row: int):
        self._cur = row
        self.text.blockSignals(True)
        self.text.setPlainText(self.items[row].text if 0 <= row < len(self.items) else "")
        self.text.blockSignals(False)

    def _text_changed(self):
        if 0 <= self._cur < len(self.items):
            p = self.items[self._cur]
            p.text = self.text.toPlainText(); p.body_html = oldimport._html(p.text)

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r); self.items.pop(r); self.show_text(self.table.currentRow())

    def row_values(self, r: int) -> dict:
        w = lambda c: self.table.cellWidget(r, c)  # noqa: E731
        return dict(kind=w(1).currentData(), number=w(2).value(), date=w(3).date().toString("yyyy-MM-dd"),
                    title=w(4).text().strip(), signer=w(5).text().strip())

    def apply(self):
        from ..backup import make_backup
        make_backup(self.db.path, "before-orders-import")
        done, failed = 0, []
        for r in range(self.table.rowCount()):
            p, v = self.items[r], self.row_values(r)
            if p.error:
                failed.append(f"{os.path.basename(p.path)}: {p.error}"); continue
            if not v["number"] or v["date"] == "2000-01-01" or not v["title"]:
                failed.append(f"{os.path.basename(p.path)}: не заповнено номер, дату або заголовок"); continue
            try:
                with open(p.path, "rb") as fh:
                    data = fh.read()
                self.db.import_order(v["kind"], v["number"], v["date"], v["title"], p.body_html, v["signer"],
                                     os.path.basename(p.path), data, p.text if p.source == "ocr" else "",
                                     notes=f"Імпортовано з {os.path.basename(p.path)} ({p.source})")
                done += 1
            except (RegistrationError, ValueError, OSError) as e:
                failed.append(f"{os.path.basename(p.path)}: {e}")
        msg = f"Записано: {done}." + (f"\n\nНе записано ({len(failed)}):\n" + "\n".join(failed[:30]) if failed else "")
        QMessageBox.information(self, "Імпорт наказів", msg)
        if done and not failed:
            self.accept()
        else:  # лишаємо в таблиці лише незаписані
            keep = {f.split(":")[0] for f in failed}
            for r in reversed(range(self.table.rowCount())):
                if os.path.basename(self.items[r].path) not in keep:
                    self.table.removeRow(r); self.items.pop(r)


_ = QWidget
