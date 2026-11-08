"""Головне вікно: бокове меню за видами, список наказів, перегляд."""
from __future__ import annotations

import datetime as dt
import html

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..db import KINDS, KIND_BY_CODE, STATUS_TITLES, Database, check_structure, format_date
from ..journal import export_journal_docx
from .order_editor import OrderEditor, TemplatePicker, create_from_template
from .theme import STYLE

ROLE = Qt.UserRole


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Накази ШКОЛА")
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)

        self.year = QComboBox()
        self.year.currentIndexChanged.connect(self.refresh)
        self.side = QTreeWidget(); self.side.setHeaderHidden(True)
        self.side.currentItemChanged.connect(lambda *_: self.reload_list())
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6)
        ll.addWidget(QLabel("Рік")); ll.addWidget(self.year); ll.addWidget(self.side, 1)

        self.search = QLineEdit(); self.search.setPlaceholderText("Пошук у наказах…")
        self.search.textChanged.connect(self.reload_list)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["№", "Дата", "Заголовок", "Вид", "Статус"])
        self.list.setRootIsDecorated(False)
        self.list.setColumnWidth(0, 70); self.list.setColumnWidth(1, 90); self.list.setColumnWidth(2, 420)
        self.list.currentItemChanged.connect(lambda *_: self.show_current())
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_current())
        mid = QWidget(); ml = QVBoxLayout(mid); ml.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        for text, slot in (("Новий наказ", self.new_order), ("Відкрити", self.edit_current),
                           ("Зареєструвати", self.register_current), ("Наказ про зміни", self.amend_current),
                           ("Скасувати", self.cancel_current), ("Зберегти DOCX/PDF…", self.export_current), ("Журнал…", self.export_journal), ("Справи…", self.open_cases), ("Перевірка", self.run_audit), ("Люди…", self.open_people), ("Імпорт наказів…", self.import_orders),
                           ("Заклад…", self.settings)):
            b = QPushButton(text); b.clicked.connect(slot); bar.addWidget(b)
        bar.addStretch()
        ml.addLayout(bar); ml.addWidget(self.search); ml.addWidget(self.list, 1)

        self.preview = QTextBrowser()
        split = QSplitter()
        split.addWidget(left); split.addWidget(mid); split.addWidget(self.preview)
        split.setSizes([230, 650, 400])
        self.setCentralWidget(split)
        self.refresh()

    # бокове меню
    def refresh(self):
        cur_year = self.year.currentData()
        self.year.blockSignals(True); self.year.clear()
        for y in self.db.years():
            self.year.addItem(str(y), y)
        if cur_year:
            self.year.setCurrentIndex(max(0, self.year.findData(cur_year)))
        self.year.blockSignals(False)
        year = self.year.currentData()
        counts = self.db.counts(year)
        sel = self.side.currentItem().data(0, ROLE) if self.side.currentItem() else ("all", None)
        self.side.blockSignals(True); self.side.clear()
        total = sum(counts.values())
        items = [QTreeWidgetItem([f"Усі накази ({total})"])]
        items[0].setData(0, ROLE, ("all", None))
        tcounts = self.db.type_counts(year)
        expanded = {self.side.topLevelItem(i).data(0, ROLE) for i in range(self.side.topLevelItemCount())
                    if self.side.topLevelItem(i).isExpanded()}
        children = []
        for k in KINDS:
            suffix = f" (-{k.suffix})" if k.suffix else ""
            it = QTreeWidgetItem([f"{k.title}{suffix}: {counts.get(k.code, 0)}"])
            it.setData(0, ROLE, ("kind", k.code)); items.append(it)
            types = [tn for (kc, tn) in tcounts if kc == k.code]
            for tn in sorted(types, key=lambda x: (x == "", x)):
                ch = QTreeWidgetItem([f"{tn or 'Без типу'}: {tcounts[(k.code, tn)]}"])
                ch.setData(0, ROLE, ("type", (k.code, tn))); it.addChild(ch); children.append(ch)
        drafts = QTreeWidgetItem([f"Чернетки ({len(self.db.list_orders(status='draft'))})"])
        drafts.setData(0, ROLE, ("draft", None)); items.append(drafts)
        self.side.addTopLevelItems(items)
        for it in items:
            it.setExpanded(it.data(0, ROLE) in expanded)
        for it in items + children:
            if it.data(0, ROLE) == sel:
                self.side.setCurrentItem(it)
        if not self.side.currentItem():
            self.side.setCurrentItem(items[0])
        self.side.blockSignals(False)
        self.reload_list()

    def reload_list(self):
        it = self.side.currentItem()
        mode, code = it.data(0, ROLE) if it else ("all", None)
        tname = None
        if mode == "type":
            code, tname = code
        rows = self.db.list_orders(kind=code if mode in ("kind", "type") else None, type_name=tname,
                                   year=None if mode == "draft" else self.year.currentData(),
                                   status="draft" if mode == "draft" else None,
                                   query=self.search.text())
        keep = self.list.currentItem().data(0, ROLE) if self.list.currentItem() else None
        self.list.clear()
        for r in rows:
            li = QTreeWidgetItem([r["reg_index"] or "–", format_date(r["date"]), r["title"],
                                  KIND_BY_CODE[r["kind"]].title, STATUS_TITLES[r["status"]]])
            li.setData(0, ROLE, r["id"])
            self.list.addTopLevelItem(li)
            if r["id"] == keep:
                self.list.setCurrentItem(li)
        if self.list.currentItem() is None:
            self.preview.clear()

    def current_row(self):
        it = self.list.currentItem()
        return self.db.get(it.data(0, ROLE)) if it else None

    def show_current(self):
        r = self.current_row()
        if not r:
            return self.preview.clear()
        head = html.escape(self.db.get_setting("school", "Назва закладу"))
        meta = f"{format_date(r['date']) or '__.__.____'} № {r['reg_index'] or '____'}"
        warn = "".join(f"<p style='color:#a35b00'>⚠ {html.escape(p.lstrip('!'))}</p>"
                       for p in check_structure(r)) if r["status"] == "draft" else ""
        sig = ("В. о. директора" if r["signer_acting"] else "Директор") + f" &nbsp; {html.escape(r['signer'])}"
        atts = "".join(f"<li>Додаток {a['n']}. {html.escape(a['title'])}</li>" for a in self.db.attachments(r["id"]))
        self.preview.setHtml(
            f"{warn}<p align=center><b>{head}</b></p><p align=center><b>НАКАЗ</b></p>"
            f"<p>{meta}</p><p><b>{html.escape(r['title'])}</b></p>{r['body_html']}"
            f"<p>{sig}</p>{'<ul>' + atts + '</ul>' if atts else ''}"
            f"<p style='color:gray'>Статус: {STATUS_TITLES[r['status']]}. {html.escape(r['notes'])}</p>")

    # дії
    def _try(self, fn):
        try:
            return fn()
        except Exception as e:  # повідомлення про помилки бази
            QMessageBox.warning(self, "Накази ШКОЛА", str(e))

    def new_order(self):
        it = self.side.currentItem()
        mode, code = it.data(0, ROLE) if it else ("all", None)
        kind = code[0] if mode == "type" else (code if mode == "kind" else None)
        dlg = TemplatePicker(self, kind, self.db)
        if dlg.exec():
            vals = dlg.values()
            oid = self._try(lambda: create_from_template(self.db, dlg.template_id, vals, kind or "osn", dlg.persons))
            self.refresh()
            if oid:
                self.open_editor(oid)

    def open_editor(self, oid: int):
        ed = OrderEditor(self.db, oid, self)
        ed.saved.connect(lambda _id: self.refresh())
        ed.show()

    def edit_current(self):
        r = self.current_row()
        if not r:
            return
        self.open_editor(r["id"])

    def register_current(self):
        r = self.current_row()
        if not r or r["status"] != "draft":
            return
        warn = [p for p in check_structure(r) if not p.startswith("!")]
        msg = f"Зареєструвати наказ від {format_date(r['date'])}? Після цього текст не змінюється."
        if warn:
            msg += "\n\nЗауваження:\n" + "\n".join(warn)
        if QMessageBox.question(self, "Реєстрація", msg) == QMessageBox.Yes:
            idx = self._try(lambda: self.db.register(r["id"]))
            if idx:
                QMessageBox.information(self, "Реєстрація", f"Наказ зареєстровано під № {idx}.")
            self.refresh()

    def amend_current(self):
        r = self.current_row()
        if r and r["status"] != "draft":
            oid = self._try(lambda: self.db.create_amendment(r["id"])); self.refresh()
            if oid:
                self.open_editor(oid)

    def cancel_current(self):
        r = self.current_row()
        if not r or r["status"] != "registered":
            return
        reason, ok = QInputDialog.getText(self, "Скасування", "Підстава (напр. наказ від … № … про скасування):")
        if ok and reason.strip():
            self._try(lambda: self.db.cancel(r["id"], reason.strip())); self.refresh()

    def export_journal(self):
        kind, ok = QInputDialog.getItem(self, "Журнал реєстрації", "Вид:", [k.journal for k in KINDS], 0, False)
        if not ok:
            return
        code = next(k.code for k in KINDS if k.journal == kind)
        year = self.year.currentData()
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти журнал", f"Журнал {code} {year}.docx", "DOCX (*.docx)")
        if path:
            self._try(lambda: export_journal_docx(self.db, code, year, path))

    def run_audit(self):
        from ..audit import audit
        found = audit(self.db)
        if not found:
            QMessageBox.information(self, "Перевірка реєстру", "Порушень не знайдено.")
            return
        text = "\n".join(f"[{lvl}] {t}" for lvl, t in found)
        QMessageBox.warning(self, "Перевірка реєстру", f"Знайдено: {len(found)}\n\n{text[:4000]}")

    def import_orders(self):
        from .oldimport_dialog import OldImportDialog
        OldImportDialog(self, self.db).exec()
        self.refresh()

    def open_cases(self):
        from .cases_dialog import CasesDialog
        CasesDialog(self, self.db, self.year.currentData()).exec()

    def open_people(self):
        from .people_window import PeopleWindow
        self._people = PeopleWindow(self.db, self); self._people.show()

    def settings(self):
        from .settings_dialog import SettingsDialog
        if SettingsDialog(self, self.db).exec():
            self.show_current()

    def export_current(self):
        r = self.current_row()
        if not r:
            return
        from ..export import export_docx, export_pdf
        name = f"Наказ {r['reg_index'] or 'чернетка'} {r['date'] or ''}".strip().replace("/", "-")
        path, flt = QFileDialog.getSaveFileName(self, "Зберегти наказ", name, "PDF (*.pdf);;Word (*.docx)")
        if not path:
            return
        fn = export_docx if path.lower().endswith(".docx") else export_pdf
        if self._try(lambda: fn(self.db, r["id"], path)):
            self.statusBar().showMessage(f"Збережено: {path}", 8000)


def _setup_log():
    """Журнал %APPDATA%/nakazy-shkola/nakazy.log: необроблені помилки пишуться туди й показуються користувачу."""
    import logging
    import os
    import sys
    from ..db import default_db_path
    path = os.path.join(os.path.dirname(default_db_path()), "nakazy.log")
    logging.basicConfig(filename=path, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Старт Накази ШКОЛА")

    def hook(tp, val, tb):
        logging.error("Необроблена помилка", exc_info=(tp, val, tb))
        try:
            QMessageBox.critical(None, "Накази ШКОЛА", f"Сталася помилка: {val}\nДеталі в журналі: {path}")
        except Exception:
            pass
    sys.excepthook = hook


def run():
    import sys
    from PySide6.QtWidgets import QApplication
    _setup_log()
    app = QApplication(sys.argv)
    w = MainWindow(Database())
    w.show()
    return app.exec()


_ = dt
