"""Вікно «Графік відпусток»: таблиця на рік → наказ про затвердження й накази про відпустку."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..db import Database, format_date
from ..importer import parse_date
from ..leave_plan import LeavePlan
from ..people import People

COLS = [("name", "Працівник"), ("vtype", "Вид (основну / додаткову)"), ("days", "Днів"), ("from_date", "З"),
        ("to_date", "По"), ("period", "Робочий рік (з … по …)"), ("note", "Примітка"), ("order", "Наказ")]
EDITABLE = {"vtype", "days", "from_date", "to_date", "period", "note"}


class LeavePlanDialog(QDialog):
    def __init__(self, parent, db: Database, year: int | None = None):
        super().__init__(parent)
        self.db, self.plan = db, LeavePlan(db)
        self.setWindowTitle("Графік відпусток")
        self.resize(1150, 560)
        self.year = QComboBox()
        import datetime as dt
        y0 = year or dt.date.today().year
        for y in range(y0 + 1, y0 - 3, -1):
            self.year.addItem(str(y), y)
        self.year.setCurrentIndex(self.year.findData(y0))
        self.year.currentIndexChanged.connect(lambda _i: self.load())
        top = QHBoxLayout(); top.addWidget(QLabel("Рік:")); top.addWidget(self.year); top.addStretch()
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in COLS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.warn = QLabel(); self.warn.setWordWrap(True); self.warn.setStyleSheet("color:#a35b00")
        btns = QHBoxLayout()
        for text, slot in (("Додати працівників…", self.add_people), ("Прибрати", self.delete_rows),
                           ("Зберегти", self.save), ("Наказ про затвердження графіка", self.schedule_order),
                           ("Накази про відпустку (окремі)", lambda: self.leave_orders(False)),
                           ("Груповий наказ про відпустки", lambda: self.leave_orders(True))):
            b = QPushButton(text); b.clicked.connect(slot); btns.addWidget(b)
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(self.reject)
        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addWidget(QLabel("Рядок – одна відпустка працівника. Накази створюються як чернетки для виділених рядків "
                           "без наказу; дати – дд.мм.рррр."))
        v.addWidget(self.table, 1); v.addWidget(self.warn); v.addLayout(btns); v.addWidget(close)
        self.load()

    def cur_year(self) -> int:
        return self.year.currentData()

    def load(self):
        self.table.setRowCount(0)
        for r in self.plan.rows(self.cur_year()):
            i = self.table.rowCount(); self.table.insertRow(i)
            order = ""
            if r["order_id"]:
                order = (r["reg_index"] or "чернетка") + (" (скасовано)" if r["order_status"] == "cancelled" else "")
            vals = {"name": f"{r['last']} {r['first']} {r['middle']}".strip(), "vtype": r["vtype"],
                    "days": "" if r["days"] is None else str(r["days"]), "from_date": format_date(r["from_date"]),
                    "to_date": format_date(r["to_date"]), "period": r["period"], "note": r["note"], "order": order}
            for c, (key, _t) in enumerate(COLS):
                it = QTableWidgetItem(vals[key])
                if key not in EDITABLE:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.UserRole, r["id"])
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()
        self.warn.setText("\n".join(f"⚠ {p}" for p in self.plan.problems(self.cur_year())))

    def add_people(self):
        dlg = QDialog(self); dlg.setWindowTitle("Працівники"); v = QVBoxLayout(dlg)
        lst = QListWidget(); lst.setSelectionMode(QAbstractItemView.MultiSelection)
        for p in People(self.db).find("staff"):
            it = QListWidgetItem(f"{p['last']} {p['first']} {p['middle']}" + (f" ({p['position']})" if p["position"] else ""))
            it.setData(Qt.UserRole, p["id"]); lst.addItem(it)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(lst); v.addWidget(bb)
        if dlg.exec():
            if not self.save(quiet=True):
                return
            for it in lst.selectedItems():
                self.plan.add(self.cur_year(), it.data(Qt.UserRole))
            self.load()

    def _row_ids(self, selected: bool) -> list[int]:
        rows = {i.row() for i in self.table.selectedIndexes()} if selected else range(self.table.rowCount())
        return [self.table.item(r, 0).data(Qt.UserRole) for r in sorted(rows)]

    def delete_rows(self):
        ids = self._row_ids(True)
        if ids and QMessageBox.question(self, "Графік", f"Прибрати рядків: {len(ids)}?") == QMessageBox.Yes:
            for i in ids:
                self.plan.delete(i)
            self.load()

    def save(self, quiet: bool = False) -> bool:
        """Записати правки таблиці; помилкові дати й дні – повідомлення, нічого не губиться."""
        errors, updates = [], []
        for r in range(self.table.rowCount()):
            cell = {key: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
                    for c, (key, _t) in enumerate(COLS)}
            f = {"vtype": cell["vtype"] or "основну", "period": cell["period"], "note": cell["note"]}
            if cell["days"] and not cell["days"].isdigit():
                errors.append(f"Рядок {r + 1}: днів – числом."); continue
            f["days"] = int(cell["days"]) if cell["days"] else None
            for key in ("from_date", "to_date"):
                d = parse_date(cell[key]) if cell[key] else None
                if cell[key] and not d:
                    errors.append(f"Рядок {r + 1}: дата «{cell[key]}» – формат дд.мм.рррр.")
                f[key] = d
            updates.append((self.table.item(r, 0).data(Qt.UserRole), f))
        if errors:
            QMessageBox.warning(self, "Графік", "\n".join(errors)); return False
        for rid, f in updates:
            self.plan.update(rid, **f)
        if not quiet:
            self.load()
        return True

    def schedule_order(self):
        if not self.save(quiet=True):
            return
        union, ok = QInputDialog.getText(self, "Графік", "Погоджено з (орудний відмінок):",
                                         text="первинною профспілковою організацією")
        if ok:
            self.plan.make_schedule_order(self.cur_year(), union)
            QMessageBox.information(self, "Графік", "Створено чернетку наказу про затвердження графіка відпусток "
                                                    "з таблицею в додатку.")

    def leave_orders(self, group: bool):
        if not self.save(quiet=True):
            return
        ids = self._row_ids(True)
        if not ids:
            QMessageBox.information(self, "Графік", "Виділіть рядки графіка."); return
        made = self.plan.make_leave_orders(ids, group)
        self.load()
        QMessageBox.information(self, "Графік", f"Створено чернеток: {len(made)}." if made else
                                "Для виділених рядків накази вже є.")
