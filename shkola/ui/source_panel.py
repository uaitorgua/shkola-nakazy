"""Крок 2: звідки беремо сторінки — вкладки «Сканування» і «Завантаження» + спільне місце вставки."""

from PySide6.QtWidgets import QFormLayout, QGroupBox, QTabWidget, QVBoxLayout

from .load_panel import LoadPanel
from .scan_panel import ScanPanel


class SourcePanel(QGroupBox):
    def __init__(self, scan: ScanPanel, load: LoadPanel) -> None:
        super().__init__("2 · Сканування або завантаження")
        self.tabs = QTabWidget()
        self.tabs.addTab(scan, "Сканування")
        self.tabs.addTab(load, "Завантаження")
        top = QFormLayout()
        top.addRow("Вставити:", scan.cb_insert)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tabs)
