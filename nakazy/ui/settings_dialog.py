"""Налаштування закладу і бланк для першої сторінки наказу."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from ..db import Database

MODES = [("text", "Текстовий (з полів нижче)"), ("image", "Зображення (скан або PNG бланка)"),
         ("docx", "Готовий бланк у Word (DOCX)")]


class SettingsDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Заклад і бланк")
        self.resize(640, 560)
        g = lambda k, d="": db.get_setting(k, d)  # noqa: E731
        self.school = QLineEdit(g("school")); self.city = QLineEdit(g("city"))
        self.head = QLineEdit(g("head")); self.head_pos = QLineEdit(g("head_position", "Директор"))
        self.size = QSpinBox(); self.size.setRange(12, 14); self.size.setValue(int(g("font_size", "14")))
        self.grif = QComboBox()
        self.grif.addItem("100 мм – ДСТУ 4163:2020 п. 7.7", "100"); self.grif.addItem("104 мм – № 676, дод. 1 п. 6", "104")
        self.grif.setCurrentIndex(max(0, self.grif.findData(g("grif_indent", "100"))))
        self.head_gen = QLineEdit(g("head_genitive", "директора"))
        self.acquaint = QCheckBox("Додавати «З наказом ознайомлені:» (ДСТУ 4163:2020 п. 5.28)")
        self.acquaint.setChecked(g("acquaint") == "1")
        top = QFormLayout()
        for label, w in (("Повна назва закладу", self.school), ("Населений пункт", self.city),
                         ("Керівник (Власне ім'я ПРІЗВИЩЕ)", self.head), ("Посада керівника", self.head_pos),
                         ("Кегль тексту (дод. 1: 12–14)", self.size), ("Відступ грифа додатка", self.grif),
                         ("У грифі «ЗАТВЕРДЖЕНО Наказ …»", self.head_gen)):
            top.addRow(label, w)
        top.addRow(self.acquaint)

        b = db.default_blank() or {"mode": "text", "fields": {}, "data": None}
        f = b["fields"]
        self.data, self.filename = b.get("data"), f.get("filename", "")
        self.mode = QComboBox()
        for code, title in MODES:
            self.mode.addItem(title, code)
        self.mode.setCurrentIndex(self.mode.findData(b["mode"]))
        self.owner = QLineEdit(f.get("owner", "")); self.bschool = QLineEdit(f.get("school", ""))
        self.address = QLineEdit(f.get("address", ""))
        self.width = QDoubleSpinBox(); self.width.setRange(30, 170); self.width.setSuffix(" мм")
        self.width.setValue(float(f.get("width_mm", 170)))
        self.has_nakaz = QCheckBox("На бланку вже надруковано слово «НАКАЗ»")
        self.has_nakaz.setChecked(bool(f.get("has_nakaz")))
        self.file_lbl = QLabel(self.filename or "файл не вибрано")
        pick = QPushButton("Вибрати файл…"); pick.clicked.connect(self._pick)
        fl = QHBoxLayout(); fl.addWidget(self.file_lbl, 1); fl.addWidget(pick)
        bf = QFormLayout()
        bf.addRow("Вид бланка", self.mode)
        bf.addRow("Орган управління (над назвою)", self.owner)
        bf.addRow("Назва закладу на бланку", self.bschool)
        bf.addRow("Адреса, код ЄДРПОУ, e-mail", self.address)
        bf.addRow("Файл бланка", fl)
        bf.addRow("Ширина зображення", self.width)
        bf.addRow(self.has_nakaz)
        bf.addRow(QLabel("Бланк друкується лише на першій сторінці наказу; поля 30/10/20/20 мм (дод. 1 п. 2)."))
        box = QGroupBox("Бланк наказу"); box.setLayout(bf)
        # редактор тексту наказів (окрема програма)
        from ..external_edit import office_exe
        self.editor = QComboBox()
        self.editor.addItem("Автоматично: «Офіс ШКОЛА», якщо встановлений, інакше програма Windows для DOCX", "auto")
        self.editor.addItem("Програма Windows для DOCX (Word, LibreOffice…)", "system")
        self.editor.addItem("Інша програма…", "custom")
        self.editor.setCurrentIndex(max(0, self.editor.findData(g("editor", "auto"))))
        self.editor_path = g("editor_path")
        self.editor_lbl = QLabel(self.editor_path or "")
        self.editor.activated.connect(self._pick_editor)
        ef = QFormLayout()
        ef.addRow("Відкривати текст у", self.editor)
        ef.addRow("", self.editor_lbl)
        ef.addRow(QLabel("«Офіс ШКОЛА»: " + ("встановлено" if office_exe() else "не знайдено (безкоштовно в Microsoft Store)")))
        ebox = QGroupBox("Редактор тексту наказів"); ebox.setLayout(ef)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        v = QVBoxLayout(self); v.addLayout(top); v.addWidget(box); v.addWidget(ebox); v.addWidget(bb)

    def _pick_editor(self, _i=None):
        if self.editor.currentData() != "custom":
            return
        path, _ = QFileDialog.getOpenFileName(self, "Програма для редагування", "", "Програми (*.exe)")
        if path:
            self.editor_path = path; self.editor_lbl.setText(path)
        elif not self.editor_path:
            self.editor.setCurrentIndex(0)

    def _pick(self):
        flt = "Бланк (*.png *.jpg *.jpeg *.docx)"
        path, _ = QFileDialog.getOpenFileName(self, "Файл бланка", "", flt)
        if path:
            with open(path, "rb") as fh:
                self.data = fh.read()
            self.filename = os.path.basename(path)
            self.file_lbl.setText(self.filename)
            self.mode.setCurrentIndex(self.mode.findData("docx" if path.lower().endswith(".docx") else "image"))

    def _save(self):
        for k, v in (("school", self.school.text()), ("city", self.city.text()), ("head", self.head.text()),
                     ("head_position", self.head_pos.text()), ("font_size", str(self.size.value())),
                     ("acquaint", "1" if self.acquaint.isChecked() else "0"), ("grif_indent", self.grif.currentData()),
                     ("head_genitive", self.head_gen.text()), ("editor", self.editor.currentData()),
                     ("editor_path", self.editor_path or "")):
            self.db.set_setting(k, v.strip())
        mode = self.mode.currentData()
        fields = {"owner": self.owner.text().strip(), "school": self.bschool.text().strip(),
                  "address": self.address.text().strip(), "width_mm": self.width.value(),
                  "has_nakaz": self.has_nakaz.isChecked(), "filename": self.filename}
        self.db.save_blank("Основний", mode, self.data if mode != "text" else None, fields)
        self.accept()
