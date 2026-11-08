"""Довідник людей: учні, працівники, класні керівники; картка з відмінками й наказами; імпорт."""
from __future__ import annotations

import html
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import importer
from ..db import Database, format_date
from ..names import CASE_TITLES
from ..people import People, school_year
from .theme import STYLE

PUPIL_COLS = [("last", "Прізвище"), ("first", "Ім'я"), ("middle", "По батькові"), ("birth", "Народж."),
              ("cls", "Клас"), ("case_no", "Особова справа")]
STAFF_COLS = [("last", "Прізвище"), ("first", "Ім'я"), ("middle", "По батькові"), ("birth", "Народж."),
              ("position", "Посада"), ("rate", "Ставка"), ("category", "Категорія")]


class PersonDialog(QDialog):
    def __init__(self, parent, ppl: People, kind: str, row=None):
        super().__init__(parent)
        self.setWindowTitle("Картка")
        self.ppl, self.kind, self.row = ppl, kind, row
        f = QFormLayout(self)
        self.e = {}
        cols = PUPIL_COLS if kind == "pupil" else STAFF_COLS
        for key, title in cols + ([("subjects", "Предмети")] if kind == "staff" else []) + [("note", "Примітка")]:
            w = QLineEdit(str(row[key] or "") if row else "")
            if key == "birth" and row and row["birth"]:
                w.setText(format_date(row["birth"]))
            self.e[key] = w; f.addRow(title, w)
        self.sex = QComboBox(); self.sex.addItem("визначити за ім'ям", ""); self.sex.addItem("чоловіча", "m")
        self.sex.addItem("жіноча", "f")
        if row:
            self.sex.setCurrentIndex(max(0, self.sex.findData(row["sex"])))
        f.addRow("Стать", self.sex)
        self.left = QCheckBox("Вибув / звільнений"); self.left.setChecked(bool(row and row["status"] == "left"))
        f.addRow(self.left)
        f.addRow(QLabel("<b>Відмінки</b> (порожнє = автоматично; виправте, якщо програма помилилась)"))
        forms = json.loads(row["forms_json"] or "{}") if row else {}
        auto = ppl.forms(row) if row else {}
        self.forms = {}
        for c in ("gen", "dat", "acc"):
            w = QLineEdit(forms.get(c, "")); w.setPlaceholderText(auto.get(c, ""))
            self.forms[c] = w; f.addRow(CASE_TITLES[c].capitalize(), w)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject); f.addRow(bb)

    def _save(self):
        v = {k: w.text().strip() for k, w in self.e.items()}
        if not v["last"]:
            QMessageBox.warning(self, "Картка", "Вкажіть прізвище."); return
        if v.get("birth"):
            b = importer.parse_date(v["birth"])
            if not b:
                QMessageBox.warning(self, "Картка", "Дата народження: формат дд.мм.рррр."); return
            v["birth"] = b
        else:
            v["birth"] = None
        if self.kind == "pupil" and v.get("cls"):
            v["cls"] = importer.norm_cls(v["cls"])
        v["sex"] = self.sex.currentData() or ""
        v["status"] = "left" if self.left.isChecked() else "active"
        if self.row:
            self.ppl.update(self.row["id"], **v); pid = self.row["id"]
        else:
            if not v["sex"]:
                v.pop("sex")
            pid = self.ppl.add(kind=self.kind, **v)
        self.ppl.set_forms(pid, {c: w.text().strip() for c, w in self.forms.items() if w.text().strip()})
        self.accept()


class ImportDialog(QDialog):
    def __init__(self, parent, db: Database, kind: str):
        super().__init__(parent)
        self.db, self.kind = db, kind
        self.setWindowTitle("Імпорт зі списку (АІКОМ2, Excel, CSV)")
        self.resize(1000, 640)
        self.rows: list[list[str]] = []
        self.plan = None
        top = QHBoxLayout()
        self.kind_cb = QComboBox(); self.kind_cb.addItem("Учні", "pupil"); self.kind_cb.addItem("Працівники", "staff")
        self.kind_cb.setCurrentIndex(self.kind_cb.findData(kind))
        pick = QPushButton("Вибрати файл XLSX/CSV…"); pick.clicked.connect(self._pick)
        self.header = QSpinBox(); self.header.setPrefix("рядок заголовків: "); self.header.setMinimum(1)
        self.header.valueChanged.connect(lambda _v: self._fill_mapping(auto=False))
        for w in (self.kind_cb, pick, self.header):
            top.addWidget(w)
        top.addStretch()
        self.table = QTableWidget()
        self.info = QTextBrowser(); self.info.setMaximumHeight(170)
        self.left = QCheckBox("Позначити як «вибув» тих, кого немає у файлі")
        prev = QPushButton("Перевірити зміни"); prev.clicked.connect(self._preview)
        self.ok = QPushButton("Імпортувати"); self.ok.setEnabled(False); self.ok.clicked.connect(self._apply)
        bl = QHBoxLayout(); bl.addWidget(self.left); bl.addStretch(); bl.addWidget(prev); bl.addWidget(self.ok)
        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addWidget(QLabel("Перевірте, яке поле в якій колонці (програма вгадала за заголовками):"))
        v.addWidget(self.table, 1); v.addWidget(self.info); v.addLayout(bl)

    def load(self, path: str):
        self.rows = importer.read_table(path)
        hi, _ = importer.detect_header(self.rows)
        self.header.blockSignals(True); self.header.setMaximum(max(1, len(self.rows))); self.header.setValue(hi + 1)
        self.header.blockSignals(False)
        self._fill_mapping(auto=True)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Список", "", "Таблиці (*.xlsx *.xlsm *.csv *.txt)")
        if path:
            try:
                self.load(path)
            except Exception as e:
                QMessageBox.warning(self, "Імпорт", f"Не вдалося прочитати файл: {e}")

    def _fill_mapping(self, auto: bool):
        if not self.rows:
            return
        hi = self.header.value() - 1
        headers = self.rows[hi]
        mapping = importer.load_mapping(self.db, headers) or (
            importer.detect_header(self.rows)[1] if auto else {j: f for j, h in enumerate(headers)
                                                               if (f := importer._match(h))})
        sample = self.rows[hi + 1: hi + 6]
        self.table.clear()
        self.table.setColumnCount(len(headers)); self.table.setRowCount(1 + len(sample))
        self.table.setHorizontalHeaderLabels([str(h) for h in headers])
        self.combos = []
        for j in range(len(headers)):
            cb = QComboBox(); cb.addItem("– не імпортувати –", None)
            for f, t in importer.FIELD_TITLES.items():
                cb.addItem(t, f)
            cb.setCurrentIndex(max(0, cb.findData(mapping.get(j))))
            self.table.setCellWidget(0, j, cb); self.combos.append(cb)
            for i, r in enumerate(sample, 1):
                self.table.setItem(i, j, QTableWidgetItem(r[j] if j < len(r) else ""))
        self.ok.setEnabled(False)

    def mapping(self) -> dict[int, str]:
        return {j: cb.currentData() for j, cb in enumerate(self.combos) if cb.currentData()}

    def _preview(self):
        if not self.rows:
            return
        m = self.mapping()
        if not ({"full", "last"} & set(m.values())):
            self.info.setHtml("<b style='color:#a35b00'>Потрібна колонка з ПІБ або прізвищем.</b>"); return
        kind = self.kind_cb.currentData()
        people, errors = importer.rows_to_people(self.rows, self.header.value() - 1, m, kind)
        self.plan = importer.make_plan(self.db, people, kind)
        self.plan.errors = errors + self.plan.errors
        ch = "".join(f"<li>{html.escape(str(old))} → {html.escape(str(new))}</li>" for _, old, new in self.plan.changed[:15])
        er = "".join(f"<li>{html.escape(e)}</li>" for e in self.plan.errors[:15])
        self.info.setHtml(f"Нових: <b>{len(self.plan.new)}</b>, змінених: <b>{len(self.plan.changed)}</b>, "
                          f"без змін: {self.plan.same}, немає у файлі: {len(self.plan.missing)}"
                          + (f"<br>Зміни:<ul>{ch}</ul>" if ch else "")
                          + (f"<br><span style='color:#a35b00'>Зауваження:</span><ul>{er}</ul>" if er else ""))
        self.ok.setEnabled(bool(self.plan.new or self.plan.changed or (self.left.isChecked() and self.plan.missing)))

    def _apply(self):
        if not self.plan:
            return
        importer.save_mapping(self.db, self.rows[self.header.value() - 1], self.mapping())
        res = importer.apply_plan(self.db, self.plan, self.left.isChecked())
        QMessageBox.information(self, "Імпорт", f"Додано: {res['new']}, оновлено: {res['changed']}, "
                                f"позначено вибулими: {res['left']}.\nПеред імпортом зроблено резервну копію.")
        self.accept()


class PeopleWindow(QMainWindow):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db, self.ppl = db, People(db)
        self.setWindowTitle("Довідник: учні й працівники · Накази ШКОЛА")
        self.resize(1200, 720); self.setStyleSheet(STYLE)
        self.tabs = QTabWidget()
        self.lists = {}
        for kind, cols in (("pupil", PUPIL_COLS), ("staff", STAFF_COLS)):
            t = QTreeWidget(); t.setHeaderLabels([c[1] for c in cols]); t.setRootIsDecorated(False)
            t.currentItemChanged.connect(lambda *_: self.show_card())
            t.itemDoubleClicked.connect(lambda *_: self.edit())
            self.lists[kind] = t
            self.tabs.addTab(t, "Учні" if kind == "pupil" else "Працівники")
        self.tabs.currentChanged.connect(lambda _i: self.reload())
        self.search = QLineEdit(); self.search.setPlaceholderText("Пошук за прізвищем, класом, посадою…")
        self.search.textChanged.connect(self.reload)
        self.cls = QComboBox(); self.cls.currentIndexChanged.connect(lambda _i: self.reload())
        self.show_left = QCheckBox("показати вибулих"); self.show_left.toggled.connect(lambda _b: self.reload())
        bar = QHBoxLayout()
        for text, slot in (("Додати", self.add), ("Змінити", self.edit), ("Імпорт…", self.do_import),
                           ("Класний керівник…", self.set_teacher)):
            b = QPushButton(text); b.clicked.connect(slot); bar.addWidget(b)
        bar.addWidget(self.search, 1); bar.addWidget(self.cls); bar.addWidget(self.show_left)
        self.card = QTextBrowser()
        left = QWidget(); lv = QVBoxLayout(left); lv.addLayout(bar); lv.addWidget(self.tabs, 1)
        sp = QSplitter(); sp.addWidget(left); sp.addWidget(self.card); sp.setSizes([800, 400])
        self.setCentralWidget(sp)
        self.reload()

    def kind(self) -> str:
        return "pupil" if self.tabs.currentIndex() == 0 else "staff"

    def reload(self):
        kind = self.kind()
        cur = self.cls.currentData()
        self.cls.blockSignals(True); self.cls.clear(); self.cls.addItem("усі класи", None)
        for c in self.ppl.classes():
            self.cls.addItem(c, c)
        self.cls.setCurrentIndex(max(0, self.cls.findData(cur))); self.cls.setVisible(kind == "pupil")
        self.cls.blockSignals(False)
        t = self.lists[kind]; t.clear()
        cols = PUPIL_COLS if kind == "pupil" else STAFF_COLS
        rows = self.ppl.find(kind, self.search.text(), not self.show_left.isChecked(),
                             self.cls.currentData() if kind == "pupil" else None)
        for r in rows:
            it = QTreeWidgetItem([format_date(r[k]) if k == "birth" else str(r[k] or "") for k, _ in cols])
            it.setData(0, Qt.UserRole, r["id"])
            if r["status"] == "left":
                for j in range(len(cols)):
                    it.setForeground(j, Qt.gray)
            t.addTopLevelItem(it)
        self.tabs.setTabText(self.tabs.currentIndex(), f"{'Учні' if kind == 'pupil' else 'Працівники'} ({len(rows)})")

    def current(self):
        it = self.lists[self.kind()].currentItem()
        return self.ppl.get(it.data(0, Qt.UserRole)) if it else None

    def show_card(self):
        r = self.current()
        if not r:
            return self.card.clear()
        f = self.ppl.forms(r)
        cases = "".join(f"<tr><td>{CASE_TITLES[c]}</td><td>{html.escape(f[c])}</td></tr>" for c in ("nom", "gen", "dat", "acc"))
        orders = "".join(f"<li>{format_date(o['date'])} № {o['reg_index'] or 'чернетка'} – {html.escape(o['title'])}</li>"
                         for o in self.ppl.orders_of(r["id"]))
        extra = f"Клас: {r['cls']}" if r["kind"] == "pupil" else f"Посада: {html.escape(r['position'])}"
        self.card.setHtml(f"<h3>{html.escape(f['nom'])}</h3><p>{extra}<br>Народження: {format_date(r['birth'])}"
                          f"<br>Статус: {'вибув' if r['status'] == 'left' else 'активний'}</p>"
                          f"<table>{cases}</table><h4>Накази</h4><ul>{orders or '<li>немає</li>'}</ul>")

    def add(self):
        if PersonDialog(self, self.ppl, self.kind()).exec():
            self.reload()

    def edit(self):
        r = self.current()
        if r and PersonDialog(self, self.ppl, r["kind"], r).exec():
            self.reload(); self.show_card()

    def do_import(self):
        d = ImportDialog(self, self.db, self.kind())
        if d.exec():
            self.reload()

    def set_teacher(self):
        cls = self.cls.currentData()
        if not cls:
            QMessageBox.information(self, "Класний керівник", "Спершу виберіть клас у фільтрі (вкладка «Учні»)."); return
        staff = self.ppl.find("staff")
        if not staff:
            QMessageBox.information(self, "Класний керівник", "Довідник працівників порожній."); return
        from PySide6.QtWidgets import QInputDialog
        names = [f"{s['last']} {s['first']} {s['middle']}" for s in staff]
        cur = self.ppl.teacher(cls)
        idx = next((i for i, s in enumerate(staff) if cur and s["id"] == cur["id"]), 0)
        name, ok = QInputDialog.getItem(self, "Класний керівник", f"{cls}, {school_year()}:", names, idx, False)
        if ok:
            self.ppl.set_teacher(cls, staff[names.index(name)]["id"])
