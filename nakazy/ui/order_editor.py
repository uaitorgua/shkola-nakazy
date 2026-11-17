"""Майстер шаблону і картка наказу. Текст наказу редагується в окремій програмі (nakazy/external_edit.py)."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QDate, QFileSystemWatcher, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDockWidget, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTextBrowser, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..db import KINDS, KIND_BY_CODE, Database, OrderLocked, check_structure, format_date
from ..templates import REFS, TEMPLATE_BY_ID, TEMPLATES, group_fields, ref_values, render, render_group


LEAVE_TEMPLATES = ("v_annual", "v_compensation", "v_recall", "v_transfer")


class TemplatePicker(QDialog):
    """Вибір шаблону (вид → тип → шаблон) і заповнення полів."""

    PERSON_KEYS = {"pupil": "pupil", "employee": "staff"}

    def __init__(self, parent, kind: str | None = None, db: Database | None = None):
        super().__init__(parent)
        self.db = db
        self.person_vals: dict[str, dict] = {}
        self.persons: dict[str, int] = {}
        self.refs: dict[str, int] = {}          # поле → id наказу-підстави
        self.ref_boxes: dict[str, QComboBox] = {}
        self.group: list[dict] | None = None    # груповий наказ: рядок на працівника (_pid – id з довідника)
        self.group_box: QCheckBox | None = None
        self.form_rows: dict = {}
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
        self.search = QLineEdit(); self.search.setPlaceholderText("Пошук шаблону: харч, відпустк, зарахув…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.search); lv.addWidget(self.tree, 1)
        lay = QHBoxLayout(); lay.addWidget(left, 1); lay.addWidget(right, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Створити")
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        v = QVBoxLayout(self); v.addLayout(lay, 1); v.addWidget(bb)
        self.edits: dict[str, QLineEdit] = {}
        self.template_id: str | None = None

    def filter(self, text: str):
        """Ховає шаблони, що не відповідають запиту; групи без збігів теж ховаються."""
        from ..templates import search
        ids = {t.id for t in search(text)}
        q = bool(text.strip())
        first = None
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.childCount() == 0:          # «Порожній наказ»
                top.setHidden(q); continue
            any_top = False
            for g in range(top.childCount()):
                grp = top.child(g); any_grp = False
                for j in range(grp.childCount()):
                    it = grp.child(j); ok = it.data(0, Qt.UserRole) in ids
                    it.setHidden(not ok); any_grp |= ok
                    if ok and first is None:
                        first = it
                grp.setHidden(not any_grp); grp.setExpanded(q and any_grp); any_top |= any_grp
            top.setHidden(not any_top)
            if q:
                top.setExpanded(any_top)
        if q and first is not None:
            self.tree.setCurrentItem(first)
        self.info.setText("" if first or not q else "Нічого не знайдено. Спробуйте коротшу частину слова.")

    def _show(self, it, _prev=None):
        tid = it.data(0, Qt.UserRole) if it else None
        w = QWidget(); f = QFormLayout(w); self.edits = {}; self.form = f
        f.setRowWrapPolicy(QFormLayout.WrapAllRows)  # підпис над полем: довгі підписи не стискають поле
        self.template_id = tid
        self.group, self.group_box, self.form_rows = None, None, {}
        if tid:
            t = TEMPLATE_BY_ID[tid]
            self.info.setText(f"<b>{KIND_BY_CODE[t.kind].title}</b> · {t.type}<br>"
                              f"Нормативна підстава (орієнтир): {t.basis or '–'}"
                              + (f"<br>Додатки: {', '.join(t.attachments)}" if t.attachments else ""))
            self.person_vals, self.persons, self.refs, self.ref_boxes = {}, {}, {}, {}
            refs = REFS.get(tid, {}) if self.db is not None else {}
            for rkey, sources in refs.items():  # наказ-підстава з реєстру (зв'язок наказів)
                cb = QComboBox(); cb.setEditable(True); cb.setInsertPolicy(QComboBox.NoInsert)
                cb.lineEdit().setPlaceholderText("вибрати з реєстру…")
                cb.completer().setFilterMode(Qt.MatchContains)
                cb.activated.connect(lambda i, k=rkey, c=cb: self._pick_ref(k, c.itemData(i)))
                self.ref_boxes[rkey] = cb
                names = ", ".join(TEMPLATE_BY_ID[s].type.lower() for s in sources)
                f.addRow(f"Наказ-підстава ({names})", cb)
            self._fill_refs()
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
                    f.addRow(label, row); self.form_rows[key] = row
                else:
                    f.addRow(label, e); self.form_rows[key] = e
            if t.group_title and self.db is not None:
                self._build_group(f, t)
        else:
            self.info.setText("Порожня чернетка." if tid == "" else "Оберіть шаблон ліворуч.")
        self.form_host.setWidget(w)
        self.template_id = tid

    # груповий наказ (кілька працівників, як «Опис пунктів» у HRMIS)
    def _build_group(self, f, t):
        self.gcols = group_fields(t)
        self.group_box = QCheckBox("Кілька працівників (груповий наказ)")
        f.insertRow(0, self.group_box)
        self.gtable = QTableWidget(0, len(self.gcols))
        self.gtable.setHorizontalHeaderLabels([lbl.split(" (")[0] for _k, lbl in self.gcols])
        self.gtable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.gtable.setMinimumHeight(180); self.gtable.horizontalHeader().setStretchLastSection(True)
        btns = QHBoxLayout()
        for text, slot in (("Додати з довідника…", self._group_from_people), ("+ рядок", lambda: self._group_add()),
                           ("Прибрати", self._group_del)):
            b = QPushButton(text); b.clicked.connect(slot); btns.addWidget(b)
        self.gwidget = QWidget(); gl = QVBoxLayout(self.gwidget); gl.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Кожен рядок – окремий пункт наказу; спільні поля – нижче."); hint.setWordWrap(True)
        gl.addWidget(hint)
        gl.addWidget(self.gtable); gl.addLayout(btns)
        f.insertRow(1, self.gwidget); f.setRowVisible(self.gwidget, False)
        self.group_box.toggled.connect(self._group_toggled)

    def _group_toggled(self, on: bool):
        self.form.setRowVisible(self.gwidget, on)
        for key, _l in self.gcols:
            if key in self.form_rows:
                self.form.setRowVisible(self.form_rows[key], not on)
        emp = self.edits.get("employee")
        if on and self.gtable.rowCount() == 0 and emp is not None and emp.text().strip():
            self._group_add(self.persons.get("employee"))  # уже вибраний працівник – перший рядок

    def _group_add(self, pid=None):
        """Новий рядок; з довідника – ПІБ, відмінки й посада підставляються."""
        r = self.gtable.rowCount(); self.gtable.insertRow(r)
        vals = {}
        if pid is not None:
            from ..people import People, person_values
            ppl = People(self.db); vals = person_values(ppl, ppl.get(pid), "employee")
        for c, (key, _l) in enumerate(self.gcols):
            text = vals.get(key) or (self.edits[key].text().strip() if key in self.edits else "")
            it = QTableWidgetItem(text)
            if c == 0:
                it.setData(Qt.UserRole, (pid, vals))
            self.gtable.setItem(r, c, it)
        self.gtable.resizeColumnsToContents()

    def _group_from_people(self):
        from ..people import People
        dlg = QDialog(self); dlg.setWindowTitle("Працівники"); v = QVBoxLayout(dlg)
        lst = QListWidget(); lst.setSelectionMode(QAbstractItemView.MultiSelection)
        for p in People(self.db).find("staff"):
            name = f"{p['last']} {p['first']} {p['middle']}" + (f" ({p['position']})" if p["position"] else "")
            it = QListWidgetItem(name); it.setData(Qt.UserRole, p["id"]); lst.addItem(it)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(lst); v.addWidget(bb)
        if dlg.exec():
            for it in lst.selectedItems():
                self._group_add(it.data(Qt.UserRole))

    def _group_del(self):
        for r in sorted({i.row() for i in self.gtable.selectedIndexes()}, reverse=True):
            self.gtable.removeRow(r)

    def _group_rows(self) -> list[dict]:
        rows = []
        for r in range(self.gtable.rowCount()):
            cells = {key: (self.gtable.item(r, c).text().strip() if self.gtable.item(r, c) else "")
                     for c, (key, _l) in enumerate(self.gcols)}
            if not cells.get("employee"):
                continue
            pid, vals = self.gtable.item(r, 0).data(Qt.UserRole) or (None, {})
            if pid is not None and vals.get("employee") == cells["employee"]:  # ПІБ не змінено – відмінки з довідника
                cells.update({k: v for k, v in vals.items() if k.startswith("employee.")})
            else:
                pid = None
            cells["_pid"] = pid
            rows.append(cells)
        return rows

    def _accept(self):
        if self.template_id is None:
            return
        self.accept()

    def _fill_refs(self):
        """Список наказів для посилання: спершу за шаблоном і вибраною людиною."""
        refs = REFS.get(self.template_id or "", {})
        for rkey, cb in self.ref_boxes.items():
            cb.blockSignals(True); cb.clear(); cb.addItem("", None)
            for r in self.db.ref_candidates(refs.get(rkey, ()), self.persons.get("employee")):
                cb.addItem(f"{format_date(r['date'])} № {r['reg_index']} {r['title']}", r["id"])
            cb.blockSignals(False)

    def _pick_ref(self, key: str, oid):
        if oid is None:
            self.refs.pop(key, None); return
        self.refs[key] = oid
        for k, v in ref_values(key, self.db.get(oid)).items():
            if k in self.edits:
                self.edits[k].setText(v)

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
        if key == "employee" and self.ref_boxes:
            self._fill_refs()
        if key == "employee" and self.template_id in LEAVE_TEMPLATES:  # залишок днів, як у HRMIS
            from ..leave import summary_html
            base = self.info.text().split("<hr>")[0]
            self.info.setText(base + "<hr>" + (summary_html(self.db, pid) or ""))

    def values(self) -> dict[str, str]:
        out = {k: e.text().strip() for k, e in self.edits.items()}
        for key, vals in self.person_vals.items():
            if out.get(key) == vals[key]:  # не змінено вручну: беремо відмінки з довідника
                out.update({k: v for k, v in vals.items() if "." in k})
            else:
                self.persons.pop(key, None)
        for key, oid in list(self.refs.items()):  # посилання лишається, лише якщо поле не змінено вручну
            if any(out.get(k) != v for k, v in ref_values(key, self.db.get(oid)).items()):
                self.refs.pop(key)
        self.group = None
        if self.group_box is not None and self.group_box.isChecked():
            self.group = self._group_rows()
            self.persons.pop("employee", None)
            for key, _l in self.gcols:
                out.pop(key, None)
        return out


class OrderEditor(QMainWindow):
    """Картка наказу: вбудований простий редактор тексту (форматування, відступи, поля, таблиці), реквізити,
    додатки. Для складнішого – «Відкрити в іншій програмі» («Офіс ШКОЛА» або програма Windows для DOCX):
    зміни після збереження файла забираються в базу."""
    saved = Signal(int)

    def __init__(self, db: Database, order_id: int, parent=None):
        super().__init__(parent)
        self.db, self.order_id = db, order_id
        row = db.get(order_id)
        self.readonly = row["status"] != "draft"
        self.imported = row["source"] == "import"
        self.can_edit = not self.readonly or self.imported
        self.edit_file: str | None = None
        self.setWindowTitle(f"{row['title'] or 'Наказ'} · Накази ШКОЛА")
        self.resize(1200, 760)
        from .text_editor import TextEditor
        self.text = TextEditor(row["body_html"], font_size=int(db.get_setting("font_size", "14") or 14))
        self.text.setReadOnly(not self.can_edit)
        self.text.changed.connect(self._text_changed)
        bar = QHBoxLayout()
        if self.can_edit:
            self.edit_btn = QPushButton("Відкрити в іншій програмі"); self.edit_btn.clicked.connect(self.start_edit)
            self.edit_btn.setToolTip("Відкрити текст у «Офіс ШКОЛА» або в програмі для DOCX (Word, LibreOffice); "
                                     "після збереження файла зміни з'являться тут")
            self.pull_btn = QPushButton("Забрати зміни з файла"); self.pull_btn.clicked.connect(self.sync_now)
            self.pull_btn.setEnabled(False)
            bar.addWidget(self.edit_btn); bar.addWidget(self.pull_btn)
        else:
            b = QPushButton("Відкрити копію для перегляду"); b.clicked.connect(self.open_copy); bar.addWidget(b)
        bar.addStretch()
        central = QWidget(); cv = QVBoxLayout(central); cv.addLayout(bar); cv.addWidget(self.text, 1)
        self.setCentralWidget(central)
        self.watcher = QFileSystemWatcher(self); self.watcher.fileChanged.connect(self._file_changed)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(800)
        self.timer.timeout.connect(self.sync_now)
        QShortcut(QKeySequence.Save, self, activated=self.save)
        self._build_dock(row)
        for sig in (self.title_e.textChanged, self.signer.textChanged, self.date.dateChanged, self.acting.toggled,
                    self.visas.textChanged):
            sig.connect(lambda *_: self._refresh_frame())
        self._refresh_frame()
        if self.imported:
            self.statusBar().showMessage("Архівний наказ (імпорт): можна виправити розпізнаний текст і заголовок; "
                                         "оригінал файла збережено.")
        elif self.readonly:
            self.statusBar().showMessage("Наказ зареєстровано: лише перегляд. Зміни вносяться новим наказом.")
        else:
            self.statusBar().showMessage("Редагуйте текст тут або кнопкою «Відкрити в іншій програмі». "
                                         "Ctrl+S – зберегти в базу.")

    def html(self) -> str:
        return self.text.html()

    def _refresh_frame(self):
        """Шапка й підпис на аркуші – як у збереженому наказі (export.py): бланк, «НАКАЗ», дата – місце – номер,
        заголовок; підпис з розшифруванням на 125 мм; «З наказом ознайомлені» за налаштуванням."""
        import html as _h

        from PySide6.QtGui import QPixmap
        from .text_editor import MARGINS, MM, PAGE_W, SIGN_MM
        db, size = self.db, self.text.font_size
        row = db.get(self.order_id)
        css = f"font-family:'Times New Roman'; color:#000;"
        text_w = int((PAGE_W - MARGINS[0] - MARGINS[1]) * MM)
        widgets = []
        blank = db.default_blank() or {"mode": "text", "fields": {}, "data": None}
        f = blank.get("fields") or {}
        if blank.get("mode") == "image" and blank.get("data"):
            pm = QPixmap(); pm.loadFromData(blank["data"])
            w = int(min(float(f.get("width_mm") or 170), 170) * MM)
            lab = QLabel(); lab.setAlignment(Qt.AlignHCenter)
            lab.setPixmap(pm.scaledToWidth(w, Qt.SmoothTransformation)); widgets.append(lab)
        elif blank.get("mode") == "docx" and blank.get("data"):
            lab = QLabel(f"<i>Бланк закладу з файла {_h.escape(f.get('filename') or 'DOCX')} – "
                         "у збереженому наказі</i>")
            lab.setAlignment(Qt.AlignHCenter); lab.setStyleSheet("color:#777; border:1px dashed #bbb; padding:8px")
            widgets.append(lab)
        else:
            school = db.get_setting("school")
            lines = []
            for key, sz, bold in (("owner", size - 2, False), ("school", size, True), ("address", size - 3, False)):
                t = f.get(key) or (school if key == "school" else "")
                if t:
                    t = _h.escape(t)
                    lines.append(f"<div style=\"{css} font-size:{sz}pt\">{'<b>' + t + '</b>' if bold else t}</div>")
            if lines:
                lab = QLabel("".join(lines)); lab.setAlignment(Qt.AlignHCenter); lab.setWordWrap(True)
                widgets.append(lab)
        city = db.get_setting("city")
        place = ("м. " + city) if city and not city.startswith(("м.", "с.", "смт")) else (city or "")
        date = self.date.date().toString("dd.MM.yyyy") if not self.readonly or row["date"] else "____________"
        number = row["reg_index"] or "______"
        gap = int(12 * 96 / 72)  # 12 пт між реквізитами, як у збереженому наказі
        if not f.get("has_nakaz"):
            lab = QLabel(f"<b style=\"{css} font-size:{size}pt\">НАКАЗ</b>"); lab.setAlignment(Qt.AlignHCenter)
            lab.setContentsMargins(0, gap, 0, 0); widgets.append(lab)
        lab = QLabel(f"<table width={text_w} cellspacing=0 cellpadding=0 style=\"{css} font-size:{size}pt\"><tr>"
                     f"<td align=left>{date}</td><td align=center>{_h.escape(place)}</td>"
                     f"<td align=right>№ {_h.escape(number)}</td></tr></table>")
        lab.setContentsMargins(0, gap, 0, 0); widgets.append(lab)
        lab = QLabel(f"<b style=\"{css} font-size:{size}pt\">{_h.escape(self.title_e.text())}</b>")
        lab.setWordWrap(True); lab.setContentsMargins(0, gap, 0, gap); widgets.append(lab)
        position = "В. о. директора" if self.acting.isChecked() else db.get_setting("head_position", "Директор")
        sign_w = int(SIGN_MM * MM)
        foot = (f"<table cellspacing=0 cellpadding=0 style=\"{css} font-size:{size}pt\"><tr>"
                f"<td width={sign_w}>{_h.escape(position)}</td><td>{_h.escape(self.signer.text())}</td></tr></table>")
        from ..export import visas_list
        for pos, name in visas_list(self.visas.text()):
            foot += (f"<p style=\"{css} font-size:{size}pt; margin-top:14pt\">{_h.escape(pos)}<br>"
                     f"____________ &nbsp; {_h.escape(name)}<br>____.____.20___</p>")
        if db.get_setting("acquaint") == "1":
            from ..export import dstu_signature
            names = [dstu_signature(x) for x in (self.responsible.text() or "").split(",") if x.strip()]
            foot += f"<p style=\"{css} font-size:{size}pt; margin-top:18pt\">З наказом ознайомлені:</p>"
            for name in names or ["", "", ""]:
                foot += (f"<table width={text_w} cellspacing=0 cellpadding=0 style=\"{css} font-size:{size}pt; "
                         f"margin-top:8pt\"><tr><td>____________</td><td>{_h.escape(name) or '______________________'}"
                         "</td><td align=right>____________</td></tr></table>")
        self.text.set_frame(widgets, foot)

    def _text_changed(self):
        if self.text.isModified() and not self.windowTitle().startswith("● "):
            self.setWindowTitle("● " + self.windowTitle())

    def _show_text(self):
        """Текст з бази в редактор (після змін з файла)."""
        self.text.setHtml(self.db.get(self.order_id)["body_html"])
        self.setWindowTitle(self.windowTitle().removeprefix("● "))

    # редагування в окремій програмі
    def start_edit(self):
        from ..external_edit import OFFICE_STORE, OFFICE_WEB, NoEditor, open_file, write_docx
        self.save()  # спершу те, що набрано тут
        self.edit_file = write_docx(self.db, self.order_id)
        self._watch()
        self.pull_btn.setEnabled(True)
        try:
            name = open_file(self.db, self.edit_file)
        except NoEditor:
            r = QMessageBox.question(
                self, "Редагування тексту",
                "На комп'ютері немає програми для документів DOCX.\n\nВстановити «Офіс ШКОЛА» з Microsoft Store? "
                "Після встановлення натисніть «Редагувати текст» ще раз.\n\nАбо виберіть програму: «Заклад…» → "
                "«Редактор тексту наказів».")
            if r == QMessageBox.Yes and not QDesktopServices.openUrl(QUrl(OFFICE_STORE)):
                QDesktopServices.openUrl(QUrl(OFFICE_WEB))
            return
        self.statusBar().showMessage(f"Текст відкрито: {name}. Збережіть файл у редакторі – зміни з'являться тут.")

    def _watch(self):
        if self.edit_file and os.path.exists(self.edit_file) and self.edit_file not in self.watcher.files():
            self.watcher.addPath(self.edit_file)

    def _file_changed(self, _path):
        self.timer.start()  # редактори пишуть файл кількома кроками

    def sync_now(self) -> bool:
        from ..external_edit import sync
        self._watch()  # деякі редактори замінюють файл новим
        if not self.edit_file or not os.path.exists(self.edit_file):
            return False
        if self.text.isModified() and QMessageBox.question(
                self, "Накази ШКОЛА", "У вікні наказу є незбережені зміни тексту. Замінити їх текстом з файла?") \
                != QMessageBox.Yes:
            return False
        try:
            changed = sync(self.db, self.order_id, self.edit_file)
        except OrderLocked as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e)); return False
        except Exception as e:  # файл ще зайнятий або пошкоджений: спробуємо при наступному збереженні
            self.statusBar().showMessage(f"Не вдалося прочитати файл: {e}"); return False
        if changed:
            from datetime import datetime
            row = self.db.get(self.order_id)
            self.title_e.setText(row["title"]); self._show_text(); self._check()
            self.setWindowTitle(f"{row['title']} · Накази ШКОЛА")
            self.statusBar().showMessage(f"Зміни з редактора збережено в базу о {datetime.now():%H:%M}. "
                                         "Попередня редакція – в історії.")
            self.saved.emit(self.order_id)
        return changed

    def open_copy(self):
        from ..external_edit import NoEditor, open_file, write_docx
        try:
            open_file(self.db, write_docx(self.db, self.order_id, copy=True))
        except NoEditor:
            QMessageBox.information(self, "Накази ШКОЛА", "Немає програми для DOCX. Скористайтеся «Зберегти наказ у "
                                                          "DOCX/PDF» і відкрийте PDF.")
        except Exception as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e))

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
        self.visas = QLineEdit(row["visas"]); self.visas.setPlaceholderText("Посада, Ім'я ПРІЗВИЩЕ; Посада, Ім'я ПРІЗВИЩЕ")
        self.visas.setToolTip("Візи погодження під підписом: посада, підпис, власне ім'я ПРІЗВИЩЕ, дата "
                              "(ДСТУ 4163:2020 п. 5.24)")
        for label, e in (("Вид", self.kind), ("Тип", self.type_name), ("Дата", self.date),
                         ("Заголовок", self.title_e), ("Підстава", self.basis), ("Підписує", self.signer),
                         ("", self.acting), ("Візи", self.visas), ("Контроль", self.controller),
                         ("Відповідальні", self.responsible), ("Примітки", self.notes)):
            f.addRow(label, e)
            e.setEnabled(not self.readonly)
        # контроль виконання: службові позначки, доступні й після реєстрації
        self.due = QLineEdit(format_date(row["due_date"]) if row["due_date"] else "")
        self.due.setPlaceholderText("дд.мм.рррр (порожньо – без строку)")
        self.due.editingFinished.connect(self._save_due)
        self.done = QCheckBox("Виконано"); self.done.setChecked(bool(row["done"]))
        self.done.setEnabled(row["status"] == "registered")
        self.done.toggled.connect(lambda on: self.db.set_done(self.order_id, on))
        f.addRow("Строк виконання", self.due); f.addRow("", self.done)
        self.atts = QListWidget(); f.addRow(QLabel("<b>Додатки</b>"))
        f.addRow(self.atts)
        ab = QHBoxLayout()
        for text, slot in (("+ текст", self._add_text_att), ("+ файл", self._add_file_att), ("Прибрати", self._del_att)):
            b = QPushButton(text); b.clicked.connect(slot); b.setEnabled(not self.readonly); ab.addWidget(b)
        f.addRow(ab)
        links = self.db.links_html(row["id"])
        if links:
            lk = QLabel("<b>Зв'язок наказів</b>" + links); lk.setWordWrap(True); f.addRow(lk)
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

    def _save_due(self):
        from ..importer import parse_date
        text = self.due.text().strip()
        iso = parse_date(text) if text else ""
        if text and not iso:
            self.statusBar().showMessage("Строк виконання: формат дд.мм.рррр."); return
        self.db.set_control(self.order_id, iso or "")
        self.saved.emit(self.order_id)

    def _values(self) -> dict:
        return dict(kind=self.kind.currentData(), type_name=self.type_name.text().strip(),
                    date=self.date.date().toString("yyyy-MM-dd"), title=self.title_e.text().strip(),
                    basis=self.basis.text().strip(), signer=self.signer.text().strip(),
                    signer_acting=int(self.acting.isChecked()), controller=self.controller.text().strip(),
                    responsible=self.responsible.text().strip(), notes=self.notes.text().strip(),
                    visas=self.visas.text().strip(), body_html=self.text.html())

    def _check(self):
        row = self.db.get(self.order_id)
        probs = check_structure(row) if row["status"] == "draft" else []
        self.warn.setText("".join(f"<p style='color:#a35b00'>⚠ {p.lstrip('!')}</p>" for p in probs))

    def save_order(self, quiet: bool = False):
        if self.readonly:
            return
        try:
            self.db.update_draft(self.order_id, **self._values())
        except OrderLocked as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e)); return
        self.text.setModified(False)
        self.setWindowTitle(self.windowTitle().removeprefix("● "))
        if quiet:
            return
        self.setWindowTitle(f"{self.title_e.text()} · Накази ШКОЛА")
        self.statusBar().showMessage("Збережено в базу")
        self._check(); self.saved.emit(self.order_id)

    def export_order(self):
        if not self.readonly:
            self.save_order(quiet=True)
        from ..export import export_docx, export_pdf
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти наказ", self.title_e.text()[:60], "PDF (*.pdf);;Word (*.docx)")
        if not path:
            return
        try:
            (export_docx if path.lower().endswith(".docx") else export_pdf)(self.db, self.order_id, path)
            from ..export import duplex_hint
            self.statusBar().showMessage(f"Збережено: {path}.{duplex_hint(self.kind.currentData())}")
        except Exception as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e))

    def save_fix(self):
        try:
            self.db.fix_imported(self.order_id, title=self.title_e.text().strip(), body_html=self.text.html(),
                                 signer=self.signer.text().strip(), notes=self.notes.text().strip())
        except OrderLocked as e:
            QMessageBox.warning(self, "Накази ШКОЛА", str(e)); return
        self.text.setModified(False)
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

    def save(self):  # Ctrl+S
        self.save_fix() if self.imported else self.save_order()

    def closeEvent(self, e):
        if getattr(self, "_closed", False) or not hasattr(self, "text"):
            return e.accept()
        if self.edit_file and os.path.exists(self.edit_file) and not self.text.isModified():
            self.sync_now()  # останні збережені в іншій програмі зміни
        if self.can_edit and self.text.isModified():
            r = QMessageBox.question(self, "Закрити", "Зберегти зміни тексту в базу?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return e.ignore()
            if r == QMessageBox.Save:
                self.save()
        self._closed = True
        e.accept()


def create_from_template(db: Database, template_id: str, values: dict[str, str], kind: str = "osn",
                         persons: dict[str, int] | None = None, refs: dict[str, int] | None = None,
                         group: list[dict] | None = None) -> int:
    """group – рядки групового наказу (поле _pid – id працівника з довідника або None)."""
    if not template_id:
        return db.create_draft(kind, title="Про ", body_html="<p>…</p><p>НАКАЗУЮ:</p><p>1. …</p>",
                               signer=db.get_setting("head"))
    t = TEMPLATE_BY_ID[template_id]
    title, body = render_group(t, values, group) if group and t.group_title else render(t, values)
    oid = db.create_draft(t.kind, title=title, body_html=body, type_name=t.type, template_id=t.id,
                          basis=t.basis, signer=db.get_setting("head"))
    from ..people import People
    ppl = People(db)
    for key, pid in (persons or {}).items():
        ppl.link(oid, pid, key)
    for key, ref_id in (refs or {}).items():
        db.link_order(oid, key, ref_id)
    db.save_values(oid, {k: v for k, v in values.items() if not k.startswith("_")},
                   [{k: v for k, v in row.items()} for row in (group or [])] if t.group_title else None)
    from ..leave import record
    if group and t.group_title:
        for row in group:
            if row.get("_pid") is not None:
                ppl.link(oid, row["_pid"], "employee")
                record(db, oid, t.id, {**values, **row}, row["_pid"], refs)
    else:
        record(db, oid, t.id, values, (persons or {}).get("employee"), refs)
    for a in t.attachments:
        body = ""
        if a.startswith("Список учнів") and values.get("cls") and ppl.find("pupil", cls=values["cls"]):
            body = ppl.class_list_html(values["cls"])
        db.add_attachment(oid, a, body_html=body, approved=t.approve)
    return oid
