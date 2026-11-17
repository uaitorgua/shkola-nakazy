"""Вікна «Нагадування» та «Алфавітна книга»."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..db import Database
from ..effects import ALPHABET_HEAD, alphabet_rows, export_alphabet_xlsx
from ..reminders import reminders


class RemindersDialog(QDialog):
    def __init__(self, parent, db: Database, open_order=None):
        super().__init__(parent)
        self.db, self.open_order = db, open_order
        self.setWindowTitle("Нагадування")
        self.resize(820, 460)
        self.list = QListWidget(); self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda *_: self.open_current())
        btns = QHBoxLayout()
        for text, slot in (("Відкрити наказ", self.open_current), ("Позначити виконаним", self.mark_done)):
            b = QPushButton(text); b.clicked.connect(slot); btns.addWidget(b)
        btns.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(self.reject)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Строк виконання й позначка «Виконано» задаються в картці наказу; рік атестації – "
                           "у картці працівника."))
        v.addWidget(self.list, 1); v.addLayout(btns); v.addWidget(close)
        self.load()

    def load(self):
        self.list.clear()
        rows = reminders(self.db)
        for r in rows:
            it = QListWidgetItem(("⚠ " if r["level"] == "увага" else "• ") + r["text"])
            it.setData(Qt.UserRole, r["order_id"])
            if r["level"] == "увага":
                it.setForeground(QColor("#a35b00"))
            self.list.addItem(it)
        if not rows:
            self.list.addItem("Нагадувань немає.")

    def _oid(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def open_current(self):
        if self._oid() and self.open_order:
            self.open_order(self._oid())

    def mark_done(self):
        oid = self._oid()
        if oid and self.db.get(oid)["status"] == "registered":
            self.db.set_done(oid, True); self.load()


class AlphabetDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Алфавітна книга учнів")
        self.resize(1100, 560)
        self.letter = QComboBox(); self.letter.currentIndexChanged.connect(lambda _i: self.fill())
        top = QHBoxLayout(); top.addWidget(QLabel("Літера:")); top.addWidget(self.letter); top.addStretch()
        self.table = QTableWidget(0, len(ALPHABET_HEAD) - 1)
        self.table.setHorizontalHeaderLabels(ALPHABET_HEAD[1:])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        exp = QPushButton("Зберегти в Excel…"); exp.clicked.connect(self.export)
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(self.reject)
        bottom = QHBoxLayout(); bottom.addWidget(exp); bottom.addStretch(); bottom.addWidget(close)
        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addWidget(QLabel("Номер особової справи видається при реєстрації наказу про зарахування (літера прізвища "
                           "і наступний номер); змінити його можна в картці учня. Вибулі – сірим."))
        v.addWidget(self.table, 1); v.addLayout(bottom)
        self.rows = alphabet_rows(db)
        self.letter.blockSignals(True)
        self.letter.addItem("усі", "")
        for ch in sorted({r["letter"] for r in self.rows}):
            self.letter.addItem(ch, ch)
        self.letter.blockSignals(False)
        self.fill()

    def fill(self):
        ch = self.letter.currentData()
        rows = [r for r in self.rows if not ch or r["letter"] == ch]
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount(); self.table.insertRow(i)
            for c, key in enumerate(("case_no", "name", "birth", "cls", "in_date", "in_order", "out_date", "out_order")):
                it = QTableWidgetItem(str(r[key] or ""))
                if r["left"]:
                    it.setForeground(QColor("#888888"))
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Алфавітна книга", "Алфавітна книга.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                export_alphabet_xlsx(self.db, path)
            except Exception as e:
                QMessageBox.warning(self, "Алфавітна книга", str(e)); return
            QMessageBox.information(self, "Алфавітна книга", f"Збережено:\n{path}")
