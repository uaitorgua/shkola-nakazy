"""Крок 4: збереження пакета — велика акцентна дія наприкінці робочого процесу."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout


class SavePanel(QGroupBox):
    save_requested = Signal()

    def __init__(self) -> None:
        super().__init__("5 · Зберегти як…")
        self.btn = QPushButton("Зберегти як… (PDF, DOCX, XLSX, TXT, графіка)")
        self.btn.setObjectName("accent")
        self.btn.clicked.connect(self.save_requested)
        self.info = QLabel("Сторінок у пакеті: 0")
        self.info.setObjectName("hint")
        lay = QVBoxLayout(self)
        lay.addWidget(self.btn)
        lay.addWidget(self.info)
        self.set_count(0)

    def set_count(self, n: int) -> None:
        self.info.setText(f"Сторінок у пакеті: {n}")
        self.btn.setEnabled(n > 0)
