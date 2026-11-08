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
        self.acquaint = QCheckBox("Додавати «З наказом ознайомлені» (практика, у № 676 не вимагається)")
        self.acquaint.setChecked(g("acquaint") == "1")
        top = QFormLayout()
        for label, w in (("Повна назва закладу", self.school), ("Населений пункт", self.city),
                         ("Керівник (Власне ім'я ПРІЗВИЩЕ)", self.head), ("Посада керівника", self.head_pos),
                         ("Кегль тексту (дод. 1: 12–14)", self.size)):
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
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        v = QVBoxLayout(self); v.addLayout(top); v.addWidget(box); v.addWidget(bb)

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
                     ("acquaint", "1" if self.acquaint.isChecked() else "0")):
            self.db.set_setting(k, v.strip())
        mode = self.mode.currentData()
        fields = {"owner": self.owner.text().strip(), "school": self.bschool.text().strip(),
                  "address": self.address.text().strip(), "width_mm": self.width.value(),
                  "has_nakaz": self.has_nakaz.isChecked(), "filename": self.filename}
        self.db.save_blank("Основний", mode, self.data if mode != "text" else None, fields)
        self.accept()
