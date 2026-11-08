"""Параметри сканування, режим (один документ / пакет), місце вставки в пакет."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QWidget,
                               QHBoxLayout, QPushButton, QRadioButton, QVBoxLayout)

from ..config import DPI_CHOICES, PAPER_SIZES
from ..core.models import ColorMode, ScanMode, ScannerInfo, ScanSettings, Source


class InsertAt(str, Enum):
    END = "У кінець пакета"
    AFTER = "Після вибраної сторінки"
    BEFORE = "Перед вибраною сторінкою"
    REPLACE = "Замінити вибрану сторінку"


class ScanPanel(QWidget):
    scan_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, store) -> None:
        super().__init__()
        self.store = store

        self.rb_single = QRadioButton(ScanMode.SINGLE.value)
        self.rb_batch = QRadioButton(ScanMode.BATCH.value)
        self.rb_batch.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_single)
        grp.addButton(self.rb_batch)
        self.rb_batch.toggled.connect(self._mode_changed)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.rb_single)
        mode_row.addWidget(self.rb_batch)

        self.cb_source = QComboBox()
        self.cb_dpi = QComboBox()
        self.cb_color = QComboBox()
        self.cb_color.addItems([c.value for c in ColorMode])
        self.cb_paper = QComboBox()
        self.cb_paper.addItems(list(PAPER_SIZES))
        self.cb_insert = QComboBox()
        self.cb_insert.addItems([i.value for i in InsertAt])

        self.chk_format = QCheckBox("Автоформат: поворот, вирівнювання, обрізання")
        self.chk_levels = QCheckBox("Автояскравість/контраст")
        auto = store.get("auto_on_scan")
        self.chk_format.setChecked(auto.get("autoformat", True))
        self.chk_levels.setChecked(auto.get("auto_levels", False))

        form = QFormLayout()
        form.addRow("Режим:", mode_row)
        form.addRow("Джерело:", self.cb_source)
        form.addRow("Роздільність, dpi:", self.cb_dpi)
        form.addRow("Колір:", self.cb_color)
        form.addRow("Формат:", self.cb_paper)

        self.btn_scan = QPushButton("Сканувати")
        self.btn_scan.setObjectName("primary")
        self.btn_scan.clicked.connect(self.scan_requested)
        self.btn_cancel = QPushButton("Скасувати")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_requested)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_scan, 1)
        btns.addWidget(self.btn_cancel)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.chk_format)
        lay.addWidget(self.chk_levels)
        lay.addLayout(btns)

        self.set_device(None)
        self._select(self.cb_color, store.get("color"))
        self._select(self.cb_paper, store.get("paper"))

    # ---------- стан ----------
    def set_device(self, info: ScannerInfo | None) -> None:
        sources = info.sources if info else (Source.FLATBED,)
        res = info.resolutions if info and info.resolutions else DPI_CHOICES
        self._refill(self.cb_source, [s.value for s in sources], self.store.get("source"))
        self._refill(self.cb_dpi, [str(r) for r in res], str(self.store.get("dpi")))
        self.btn_scan.setEnabled(info is not None)

    def set_scanning(self, on: bool) -> None:
        self.btn_scan.setEnabled(not on)
        self.btn_cancel.setEnabled(on)

    def settings(self) -> ScanSettings:
        s = ScanSettings(
            dpi=int(self.cb_dpi.currentText() or 300),
            color=ColorMode(self.cb_color.currentText()),
            source=Source(self.cb_source.currentText()),
            paper=self.cb_paper.currentText(),
        )
        self.store.data.update(dpi=s.dpi, color=s.color.value, source=s.source.value, paper=s.paper,
                               auto_on_scan=self.auto())
        self.store.save()
        return s

    def mode(self) -> ScanMode:
        return ScanMode.BATCH if self.rb_batch.isChecked() else ScanMode.SINGLE

    def insert_at(self) -> InsertAt:
        return InsertAt(self.cb_insert.currentText())

    def auto(self) -> dict:
        return {"autoformat": self.chk_format.isChecked(), "auto_levels": self.chk_levels.isChecked()}

    def _mode_changed(self) -> None:
        self.cb_insert.setEnabled(True)   # спільне з «Завантаженням»

    @staticmethod
    def _refill(cb: QComboBox, items: list[str], prefer: str) -> None:
        cur = cb.currentText() or prefer
        cb.clear()
        cb.addItems(items)
        ScanPanel._select(cb, cur)

    @staticmethod
    def _select(cb: QComboBox, text: str) -> None:
        i = cb.findText(str(text))
        if i >= 0:
            cb.setCurrentIndex(i)
