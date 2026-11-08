"""Номенклатура справ на рік: індекси, назви, строки зберігання, статті Переліку; формування справи."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QProgressDialog, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..cases import Cases, export_case_pdf
from ..db import KIND_BY_CODE, Database

COLS = [("case_index", "Індекс справи"), ("title", "Заголовок справи"), ("retention", "Строк зберігання"),
        ("article", "Стаття Переліку 578/5"), ("note", "Примітка")]


class CasesDialog(QDialog):
    def __init__(self, parent, db: Database, year: int):
        super().__init__(parent)
        self.db, self.cases = db, Cases(db)
        self.setWindowTitle("Номенклатура справ і строки зберігання")
        self.resize(1150, 520)
        self.year = QComboBox()
        for y in sorted(set(db.years()) | {year, year + 1}, reverse=True):
            self.year.addItem(str(y), y)
        self.year.setCurrentIndex(self.year.findData(year))
        self.year.currentIndexChanged.connect(lambda _i: self.load())
        top = QHBoxLayout(); top.addWidget(QLabel("Рік:")); top.addWidget(self.year); top.addStretch()
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in COLS])
        for i, w in enumerate((110, 470, 120, 150)):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._changed)
        self.info = QLabel(); self.info.setWordWrap(True)
        bl = QHBoxLayout()
        b = QPushButton("Сформувати справу (PDF)…"); b.clicked.connect(self.export_case); bl.addWidget(b)
        bl.addStretch()
        close = QPushButton("Закрити"); close.clicked.connect(self.accept); bl.addWidget(close)
        v = QVBoxLayout(self); v.addLayout(top)
        v.addWidget(QLabel("Строки за Переліком 578/5 (наказ Мін'юсту від 12.04.2012). Номенклатура затверджується "
                           "не пізніше 20 грудня й діє з 1 січня (Інструкція МОН № 676, р. V п. 12). "
                           "Номер статті звірте з чинною редакцією Переліку на zakon.rada.gov.ua."))
        v.addWidget(self.table, 1); v.addWidget(self.info); v.addLayout(bl)
        self.load()

    def load(self):
        y = self.year.currentData()
        self.table.blockSignals(True)
        rows = self.cases.items(y)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, (k, _t) in enumerate(COLS):
                it = QTableWidgetItem(r[k]); it.setData(Qt.UserRole, (r["kind"], r["part"]))
                self.table.setItem(i, j, it)
        self.table.blockSignals(False)
        self._problems()

    def _changed(self, it: QTableWidgetItem):
        kind, part = it.data(Qt.UserRole)
        self.cases.update(self.year.currentData(), kind, part, **{COLS[it.column()][0]: it.text().strip()})
        self._problems()

    def _problems(self):
        p = self.cases.problems(self.year.currentData())
        self.info.setText("<span style='color:#a35b00'>" + "<br>".join(f"⚠ {x}" for x in p) + "</span>" if p
                          else "Номенклатура заповнена.")

    def export_case(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "Справа", "Виберіть рядок справи з наказами."); return
        kind, part = self.table.item(r, 0).data(Qt.UserRole)
        if part != "orders":
            QMessageBox.information(self, "Справа", "Журнал реєстрації друкується кнопкою «Журнал…» у головному вікні.")
            return
        y = self.year.currentData()
        if not self.db.journal(kind, y):
            QMessageBox.information(self, "Справа", f"За {y} рік наказів виду «{KIND_BY_CODE[kind].title}» немає."); return
        idx = self.table.item(r, 0).text() or kind
        path, _ = QFileDialog.getSaveFileName(self, "Справа", f"Справа {idx} {y}.pdf", "PDF (*.pdf)")
        if not path:
            return
        prog = QProgressDialog("Формую справу…", None, 0, 100, self); prog.setWindowModality(Qt.WindowModal)

        def step(i, n):
            prog.setValue(int(i * 100 / max(n, 1))); QApplication.processEvents()
        try:
            export_case_pdf(self.db, kind, y, path, step)
            prog.setValue(100)
            QMessageBox.information(self, "Справа", f"Збережено: {path}")
        except Exception as e:
            prog.close(); QMessageBox.warning(self, "Справа", str(e))
