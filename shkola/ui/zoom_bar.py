"""Панель масштабу під переглядом сторінки: −, повзунок, відсотки, +, «Вмістити», «100 %»."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from .image_view import ZOOM_MAX, ZOOM_MIN, ImageView

_STEPS = 200   # положень повзунка (логарифмічна шкала)


def _to_slider(z: float) -> int:
    return round((math.log(z) - math.log(ZOOM_MIN)) / (math.log(ZOOM_MAX) - math.log(ZOOM_MIN)) * _STEPS)


def _from_slider(v: int) -> float:
    return math.exp(math.log(ZOOM_MIN) + v / _STEPS * (math.log(ZOOM_MAX) - math.log(ZOOM_MIN)))


class ZoomBar(QWidget):
    def __init__(self, view: ImageView) -> None:
        super().__init__()
        self.view = view
        self.setObjectName("zoombar")
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(6)

        def btn(text, slot, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        self.setToolTip("Колесо миші — масштаб; перетягування мишею (або середня / права кнопка) — пересування документа")
        lay.addStretch(1)
        btn("−", lambda: view.zoom(0.8), "Зменшити (Ctrl+−)").setFixedWidth(30)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, _STEPS)
        self.slider.setFixedWidth(110)
        self.slider.setToolTip(self.toolTip())
        self.slider.valueChanged.connect(self._slide)
        lay.addWidget(self.slider)
        btn("+", lambda: view.zoom(1.25), "Збільшити (Ctrl+=)").setFixedWidth(30)
        self.pct = QLabel("100 %")
        self.pct.setFixedWidth(48)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.pct)
        btn("Вмістити", view.fit, "Умістити сторінку у вікно (Ctrl+0)")
        btn("1:1", view.zoom_100, "Справжній розмір (100 %)").setFixedWidth(40)
        lay.addStretch(1)

        self._busy = False
        view.zoom_changed.connect(self._sync)
        self._sync(view.zoom_factor())

    def _sync(self, z: float) -> None:
        self._busy = True
        self.slider.setValue(_to_slider(max(ZOOM_MIN, min(ZOOM_MAX, z))))
        self.pct.setText(f"{z * 100:.0f} %")
        self._busy = False

    def _slide(self, v: int) -> None:
        if not self._busy:
            self.view.set_zoom(_from_slider(v))
