"""Редактор наказу: InterText (зі «Сканер ШКОЛА») + панель реквізитів, збереження в базу."""
from __future__ import annotations

import re

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from shkola.ui.editor_window import EditorWindow

from ..db import KINDS, KIND_BY_CODE, Database, OrderLocked, check_structure
from ..templates import TEMPLATE_BY_ID, TEMPLATES, render


class TemplatePicker(QDialog):
    """Вибір шаблону (вид → тип → шаблон) і заповнення полів."""

    PERSON_KEYS = {"pupil": "pupil", "employee": "staff"}

    def __init__(self, parent, kind: str | None = None, db: Database | None = None):
        super().__init__(parent)
        self.db = db
        self.person_vals: dict[str, dict] = {}
        self.persons: dict[str, int] = {}
        self.setWindowTitle("Новий наказ за шаблоном")
        self.resize(900, 600)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        for k in KINDS:
            top = QTreeWidgetItem([k.title]); self.tree.addTopLevelItem(top)
            groups: dict[str, QTreeWidgetItem] = {}
            for t in TEMPLATES:
                if t.kind != k.code:
                    continue
                g = groups.get(t.type)
                if g is None:
                    g = groups[t.type] = QTreeWidgetItem([t.type]); top.addChild(g)
                labels = {k: l.split(" (")[0].lower() for k, l in t.fields}
                shown = re.sub(r"\{(\w+)(?:\.\w+)?\}", lambda m: f"‹{labels.get(m.group(1), m.group(1))}›", t.title)
                it = QTreeWidgetItem([shown])
                it.setData(0, Qt.UserRole, t.id); g.addChild(it)
            top.setExpanded(kind in (None, k.code))
        empty = QTreeWidgetItem(["Порожній наказ (без шаблону)"]); empty.setData(0, Qt.UserRole, "")
        self.tree.addTopLevelItem(empty)
        self.tree.currentItemChanged.connect(self._show)
        self.form_host = QScrollArea(); self.form_host.setWidgetResizable(True)
        self.info = QLabel(); self.info.setWordWrap(True)
        right = QWidget(); rl = QVBoxLayout(right); rl.addWidget(self.info); rl.addWidget(self.form_host, 1)
        lay = QHBoxLayout(); lay.addWidget(self.tree, 1); lay.addWidget(right, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Створити")
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        v = QVBoxLayout(self); v.addLayout(lay, 1); v.addWidget(bb)
        self.edits: dict[str, QLineEdit] = {}
        self.template_id: str | None = None

    def _show(self, it, _prev=None):
        tid = it.data(0, Qt.UserRole) if it else None
        w = QWidget(); f = QFormLayout(w); self.edits = {}
        if tid:
            t = TEMPLATE_BY_ID[tid]
            self.info.setText(f"<b>{KIND_BY_CODE[t.kind].title}</b> · {t.type}<br>"
                              f"Нормативна підстава (орієнтир): {t.basis or '–'}"
                              + (f"<br>Додатки: {', '.join(t.attachments)}" if t.attachments else ""))
            self.person_vals, self.persons = {}, {}
            for key, label in t.fields:
                e = QLineEdit(); self.edits[key] = e
                if key in self.PERSON_KEYS and self.db is not None:
                    row = QVBoxLayout(); row.setSpacing(4)
                    cb = QComboBox(); cb.setEditable(True)
                    cb.lineEdit().setPlaceholderText("вибрати з довідника…")
                    from ..people import People
                    cb.addItem("", None)
                    for p in People(self.db).find(self.PERSON_KEYS[key]):
                        extra = p["cls"] or p["position"]
                        cb.addItem(f"{p['last']} {p['first']} {p['middle']}" + (f" ({extra})" if extra else ""), p["id"])
                    cb.setInsertPolicy(QComboBox.NoInsert)
                    cb.completer().setFilterMode(Qt.MatchContains)
                    cb.activated.connect(lambda i, k=key, c=cb: self._pick_person(k, c.itemData(i)))
                    row.addWidget(cb); row.addWidget(e); e.setPlaceholderText("або введіть вручну")
                    f.addRow(label, row)
                else:
                    f.addRow(label, e)
        else:
            self.info.setText("Порожня чернетка." if tid == "" else "Оберіть шаблон ліворуч.")
        self.form_host.setWidget(w)
        self.template_id = tid

    def _accept(self):
        if self.template_id is None:
            return
        self.accept()

    def _pick_person(self, key: str, pid):
        if pid is None:
            return
        from ..people import People, person_values
        ppl = People(self.db)
        vals = person_values(ppl, ppl.get(pid), key)
        self.person_vals[key], self.persons[key] = vals, pid
        self.edits[key].setText(vals[key])
        for k, v in vals.items():  # клас, дата народження, посада
            if "." not in k and k != key and k in self.edits and not self.edits[k].text().strip():
                self.edits[k].setText(v)

    def values(self) -> dict[str, str]:
        out = {k: e.text().strip() for k, e in self.edits.items()}
        for key, vals in self.person_vals.items():
            if out.get(key) == vals[key]:  # не змінено вручну: беремо відмінки з довідника
                out.update({k: v for k, v in vals.items() if "." in k})
            else:
                self.persons.pop(key, None)
        return out


class OrderEditor(EditorWindow):
    saved = Signal(int)

    def __init__(self, db: Database, order_id: int, parent=None):
        self.db, self.order_id = db, order_id
        row = db.get(order_id)
        super().__init__(parent, html=row["body_html"], title=row["title"] or "Наказ")
        self.readonly = row["status"] != "draft"
        self.imported = row["source"] == "import"
        self._build_dock(row)
        if self.imported:
            self.statusBar().showMessage("Архівний наказ (імпорт): можна виправити розпізнаний текст і заголовок; "
                                         "оригінал файла збережено.")
        elif self.readonly:
            self.edit.setReadOnly(True)
            self.statusBar().showMessage("Наказ зареєстровано: лише перегляд. Зміни вносяться новим наказом.")

    def _build_dock(self, row):
        w = QWidget(); f = QFormLayout(w)
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(k.title, k.code)
        self.kind.setCurrentIndex(self.kind.findData(row["kind"]))
        self.type_name = QLineEdit(row["type_name"])
        self.date = QDateEdit(QDate.fromString(row["date"], "yyyy-MM-dd") if row["date"] else QDate.currentDate())
        self.date.setCalendarPopup(True); self.date.setDisplayFormat("dd.MM.yyyy")
        self.title_e = QLineEdit(row["title"])
        self.basis = QLineEdit(row["basis"])
        self.signer = QLineEdit(row["signer"] or self.db.get_setting("head"))
        self.acting = QCheckBox("в. о. керівника"); self.acting.setChecked(bool(row["signer_acting"]))
        self.controller = QLineEdit(row["controller"]); self.responsible = QLineEdit(row["responsible"])
        self.notes = QLineEdit(row["notes"])
        for label, e in (("Вид", self.kind), ("Тип", self.type_name), ("Дата", self.date),
                         ("Заголовок", self.title_e), ("Підстава", self.basis), ("Підписує", self.signer),
                         ("", self.acting), ("Контроль", self.controller), ("Відповідальні", self.responsible),
                         ("Примітки", self.notes)):
            f.addRow(label, e)
            e.setEnabled(not self.readonly)
        self.atts = QListWidget(); f.addRow(QLabel("<b>Додатки</b>"))
        f.addRow(self.atts)
        ab = QHBoxLayout()
        for text, slot in (("+ текст", self._add_text_att), ("+ файл", self._add_file_att), ("Прибрати", self._del_att)):
            b = QPushButton(text); b.clicked.connect(slot); b.setEnabled(not self.readonly); ab.addWidget(b)
        f.addRow(ab)
        self.warn = QLabel(); self.warn.setWordWrap(True); f.addRow(self.warn)
        save = QPushButton("Зберегти в базу (Ctrl+S)"); save.clicked.connect(self.save_order)
        save.setEnabled(not self.readonly); f.addRow(save)
        if row["source"] == "import":
            fix = QPushButton("Зберегти виправлення розпізнаного"); fix.clicked.connect(self.save_fix)
            orig = QPushButton("Відкрити оригінал"); orig.clicked.connect(self.open_original)
            self.title_e.setEnabled(True); self.signer.setEnabled(True); self.notes.setEnabled(True)
            f.addRow(fix); f.addRow(orig)
        exp = QPushButton("Зберегти наказ у DOCX/PDF (з бланком)"); exp.clicked.connect(self.export_order)
        f.addRow(exp)
        dock = QDockWidget("Реквізити наказу", self); dock.setWidget(w)
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._reload_atts(); self._check()

    def _reload_atts(self):
        self.atts.clear()
        for a in self.db.attachments(self.order_id):
            src = "текст" if a["mode"] == "text" else (a["filename"] or "файл")
            it = QListWidgetItem(f"{'ЗАТВЕРДЖЕНО' if a['approved'] else 'Додаток'} {a['n']}. {a['title']} ({src})"); it.setData(Qt.UserRole, a["id"])
            self.atts.addItem(it)

    def _add_text_att(self):
        t, ok = QInputDialog.getText(self, "Додаток", "Назва додатка:")
        if ok and t.strip():
            appr = QMessageBox.question(self, "Додаток", "Цей документ затверджується наказом "
                                        "(план, графік, склад комісії)?\nТоді замість «Додаток N» буде гриф «ЗАТВЕРДЖЕНО».")
            self.db.add_attachment(self.order_id, t.strip(), approved=appr == QMessageBox.Yes); self._reload_atts()

    def _add_file_att(self):
        path, _ = QFileDialog.getOpenFileName(self, "Файл додатка", "", "Документи (*.pdf *.docx *.xlsx *.png *.jpg)")
        if not path:
            return
        import os
        t, ok = QInputDialog.getText(self, "Додаток", "Назва додатка:", text=os.path.splitext(os.path.basename(path))[0])
        if ok:
            with open(path, "rb") as fh:
                self.db.add_attachment(self.order_id, t.strip(), "file", filename=os.path.basename(path), data=fh.read())
            self._reload_atts()

    def _del_att(self):
        it = self.atts.currentItem()
        if it:
            self.db.remove_attachment(it.data(Qt.UserRole)); self._reload_atts()

    def _values(self) -> dict:
        return dict(kind=self.kind.currentData(), type_name=self.type_name.text().strip(),
                    date=self.date.date().toString("yyyy-MM-dd"), title=self.title_e.text().strip(),
                    basis=self.basis.text().strip(), signer=self.signer.text().strip(),
                    signer_acting=int(self.acting.isChecked()), controller=self.controller.text().strip(),
                    responsible=self.responsible.text().strip(), notes=self.notes.text().strip(),
                    body_html=self.html())

    def _check(self):
        row = self.db.get(self.order_id)
        probs = check_structure(row) if row["status"] == "draft" else []
        self.warn.setText("".join(f"<p style='color:#a35b00'>⚠ {p.lstrip('!')}</p>" for p in probs))

    def save_order(self):
        if self.readonly:
            return
        try:
            self.db.update_draft(self.order_id, **self._values())
        except OrderLocked as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e)); return
        self.edit.document().setModified(False)
        self.setWindowTitle(f"{self.title_e.text()} · Накази ШКОЛА")
        self.statusBar().showMessage("Збережено в базу")
        self._check(); self.saved.emit(self.order_id)

    def export_order(self):
        if not self.readonly and self.edit.document().isModified():
            self.save_order()
        from ..export import export_docx, export_pdf
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти наказ", self.title_e.text()[:60], "PDF (*.pdf);;Word (*.docx)")
        if not path:
            return
        try:
            (export_docx if path.lower().endswith(".docx") else export_pdf)(self.db, self.order_id, path)
            self.statusBar().showMessage(f"Збережено: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e))

    def save_fix(self):
        try:
            self.db.fix_imported(self.order_id, title=self.title_e.text().strip(), body_html=self.html(),
                                 signer=self.signer.text().strip(), notes=self.notes.text().strip())
        except OrderLocked as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e)); return
        self.edit.document().setModified(False)
        self.statusBar().showMessage("Виправлення збережено (попередня версія в історії)")
        self.saved.emit(self.order_id)

    def open_original(self):
        o = self.db.original(self.order_id)
        if not o:
            return
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), o["filename"])
        with open(path, "wb") as fh:
            fh.write(o["data"])
        os.startfile(path)  # відкрити у програмі за замовчуванням Windows

    def save(self):  # Ctrl+S у стрічці InterText
        self.save_fix() if self.imported else self.save_order()

    def closeEvent(self, e):
        if self.imported and self.edit.document().isModified():
            if QMessageBox.question(self, "Закрити", "Зберегти виправлення розпізнаного?") == QMessageBox.Yes:
                self.save_fix()
        elif not self.readonly and self.edit.document().isModified():
            r = QMessageBox.question(self, "Закрити", "Зберегти зміни в базу?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                e.ignore(); return
            if r == QMessageBox.Save:
                self.save_order()
        e.accept()


def create_from_template(db: Database, template_id: str, values: dict[str, str], kind: str = "osn",
                         persons: dict[str, int] | None = None) -> int:
    if not template_id:
        return db.create_draft(kind, title="Про ", body_html="<p>…</p><p>НАКАЗУЮ:</p><p>1. …</p>",
                               signer=db.get_setting("head"))
    t = TEMPLATE_BY_ID[template_id]
    title, body = render(t, values)
    oid = db.create_draft(t.kind, title=title, body_html=body, type_name=t.type, template_id=t.id,
                          basis=t.basis, signer=db.get_setting("head"))
    from ..people import People
    ppl = People(db)
    for key, pid in (persons or {}).items():
        ppl.link(oid, pid, key)
    for a in t.attachments:
        body = ""
        if a.startswith("Список учнів") and values.get("cls") and ppl.find("pupil", cls=values["cls"]):
            body = ppl.class_list_html(values["cls"])
        db.add_attachment(oid, a, body_html=body, approved=t.approve)
    return oid
