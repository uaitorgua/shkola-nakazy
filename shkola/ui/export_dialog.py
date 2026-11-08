"""Діалог збереження: PDF, PDF з текстовим шаром, DOCX, XLSX, TXT або графіка (по сторінках / TIFF)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox, QWidget)

from ..export.image_export import FORMATS
from ..export.naming import safe_name, stamp

DOC_FORMATS = [
    ("pdf", "PDF (зображення сторінок)"),
    ("pdf_text", "PDF з текстовим шаром (пошук і копіювання тексту)"),
    ("docx", "Документ DOCX (текст, заголовки, списки, таблиці)"),
    ("xlsx", "Таблиця XLSX (таблиці зі сторінок)"),
    ("txt", "Текст TXT"),
]
NEEDS_OCR = {"pdf_text", "docx", "xlsx", "txt"}


class ExportDialog(QDialog):
    def __init__(self, parent, store, n_selected: int, n_total: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Зберегти")
        self.store = store

        self.cb_format = QComboBox()
        self.cb_format.addItems([t for _, t in DOC_FORMATS] + [f"Графіка: {k}" for k in FORMATS])
        self.cb_format.setCurrentIndex(0)
        self.ed_name = QLineEdit(f"{store.get('file_prefix')}_{stamp()}")
        self.ed_dir = QLineEdit(store.get("output_dir"))
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.addWidget(self.ed_dir)
        dir_row.addWidget(browse)
        dir_w = QWidget()
        dir_w.setLayout(dir_row)
        self.sp_quality = QSpinBox()
        self.sp_quality.setRange(30, 100)
        self.sp_quality.setValue(int(store.get("jpeg_quality")))
        self.sp_quality.setSuffix(" %")
        self.rb_all = QRadioButton(f"Усі сторінки ({n_total})")
        self.rb_sel = QRadioButton(f"Лише вибрані ({n_selected})")
        self.rb_all.setChecked(True)
        self.rb_sel.setEnabled(0 < n_selected < n_total)
        which = QHBoxLayout()
        which.addWidget(self.rb_all)
        which.addWidget(self.rb_sel)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.cb_format.currentIndexChanged.connect(self._hint)
        self._hint()

        form = QFormLayout(self)
        form.addRow("Формат:", self.cb_format)
        form.addRow("", self.hint)
        form.addRow("Назва:", self.ed_name)
        form.addRow("Тека:", dir_w)
        form.addRow("Якість JPEG/PDF:", self.sp_quality)
        form.addRow("Сторінки:", which)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.resize(560, 0)

    def _hint(self) -> None:
        self.hint.setText("Нерозпізнані сторінки будуть розпізнані перед збереженням."
                          if self.kind() in NEEDS_OCR else "")

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Тека для збереження", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    # Результат
    def kind(self) -> str:
        i = self.cb_format.currentIndex()
        return DOC_FORMATS[i][0] if i < len(DOC_FORMATS) else "image"

    def is_pdf(self) -> bool:
        return self.kind() == "pdf"

    def image_format(self) -> str:
        return self.cb_format.currentText().removeprefix("Графіка: ")

    def folder(self) -> Path:
        return Path(self.ed_dir.text())

    def name(self) -> str:
        return safe_name(self.ed_name.text())

    def quality(self) -> int:
        return self.sp_quality.value()

    def only_selected(self) -> bool:
        return self.rb_sel.isChecked()

    def remember(self) -> None:
        self.store.data.update(output_dir=str(self.folder()), jpeg_quality=self.quality())
        self.store.save()
