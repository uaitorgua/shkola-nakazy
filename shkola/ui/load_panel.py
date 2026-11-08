"""Вкладка «Завантаження»: додавання готових PDF і зображень замість сканування."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..importing import loader


class LoadPanel(QWidget):
    open_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.btn = QPushButton("Обрати файли…")
        self.btn.setObjectName("primary")
        self.btn.clicked.connect(self.open_requested)
        self.cb_pdf_dpi = QComboBox()
        self.cb_pdf_dpi.addItems(["150", "200", "300", "400"])
        self.cb_pdf_dpi.setCurrentText(str(loader.PDF_DPI))
        self.cb_pdf_dpi.currentTextChanged.connect(lambda t: setattr(loader, "PDF_DPI", int(t)))
        self.chk_format = QCheckBox("Автоформат: поворот, вирівнювання, обрізання")
        hint = QLabel("PDF (усі сторінки), JPG, PNG, TIFF (багатосторінкові), BMP, WEBP, HEIC.\n"
                      "Можна просто перетягнути файли у вікно.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Якість PDF, dpi:", self.cb_pdf_dpi)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.chk_format)
        lay.addWidget(hint)
        lay.addStretch(1)
        lay.addWidget(self.btn)
