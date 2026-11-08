"""Панель правок сторінки: поворот, вирівнювання, кадр, тон, фільтр."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from ..core.models import Adjust
from ..imaging.filters import FILTERS


class _Slider(QWidget):
    changed = Signal()

    def __init__(self, lo: int, hi: int, scale: float = 1.0) -> None:
        super().__init__()
        self.scale = scale
        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setRange(lo, hi)
        self.lbl = QLabel()
        self.lbl.setFixedWidth(38)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.s)
        lay.addWidget(self.lbl)
        self.s.valueChanged.connect(self._upd)
        self._upd()

    def _upd(self) -> None:
        v = self.value()
        self.lbl.setText(f"{v:.2f}" if self.scale != 1 else str(int(v)))
        self.changed.emit()

    def value(self):
        return self.s.value() * self.scale

    def set_value(self, v) -> None:
        self.s.blockSignals(True)
        self.s.setValue(round(v / self.scale))
        self.s.blockSignals(False)
        self.lbl.setText(f"{v:.2f}" if self.scale != 1 else str(int(v)))


class AdjustPanel(QGroupBox):
    adjust_changed = Signal(object)        # Adjust (безперервно, під час руху повзунків)
    action = Signal(str)                   # rotate_l, rotate_r, deskew, autocrop, auto, reset, crop_mode, crop_clear, apply_all

    def __init__(self) -> None:
        super().__init__("3 · Правка сторінки")
        self._adj = Adjust()
        self._loading = False

        def btn(text, act, tip=""):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda: self.action.emit(act))
            return b

        self.btn_auto = btn("✨ Автопокращення", "auto", "Вирівняти, обрізати поля, автоконтраст")
        self.btn_auto.setObjectName("primary")

        self.btn_format = btn("Автоформат", "autoformat", "Поворот за текстом, вирівнювання, обрізання зайвого")

        geo = QGridLayout()
        geo.addWidget(btn("⟲ 90°", "rotate_l"), 0, 0)
        geo.addWidget(btn("⟳ 90°", "rotate_r"), 0, 1)
        geo.addWidget(btn("Вирівняти", "deskew", "Автоматично прибрати перекіс"), 1, 0)
        geo.addWidget(btn("Обрізати поля", "autocrop", "Автоматично знайти межі аркуша"), 1, 1)
        self.btn_crop = QPushButton("✂ Кадрувати")
        self.btn_crop.setCheckable(True)
        self.btn_crop.setToolTip("Рамка мишею: тягніть кути/краї, перетягуйте всередині")
        self.btn_crop.toggled.connect(lambda on: self.action.emit("crop_mode" if on else "crop_off"))
        geo.addWidget(self.btn_crop, 2, 0)
        geo.addWidget(btn("Скинути кадр", "crop_clear"), 2, 1)
        geo.addWidget(btn("Визначити формат", "template",
                          "A4, A5, диплом, ID-картка, фото 13×18, 10×15… — обрізати точно під шаблон"), 3, 0, 1, 2)

        self.angle = QDoubleSpinBox()
        self.angle.setRange(-45, 45)
        self.angle.setSingleStep(0.1)
        self.angle.setDecimals(2)
        self.angle.setSuffix("°")
        self.angle.valueChanged.connect(self._emit)
        self.brightness = _Slider(-100, 100)
        self.contrast = _Slider(-100, 100)
        self.gamma = _Slider(20, 300, 0.01)
        self.gamma.set_value(1.0)
        self.auto_levels = QCheckBox("Автоматичні рівні")
        self.filter = QComboBox()
        for k, v in FILTERS.items():
            self.filter.addItem(v, k)
        for w in (self.brightness, self.contrast, self.gamma):
            w.changed.connect(self._emit)
        self.auto_levels.toggled.connect(self._emit)
        self.filter.currentIndexChanged.connect(self._emit)

        tone = QGridLayout()
        rows = [("Кут нахилу:", self.angle), ("Яскравість:", self.brightness), ("Контраст:", self.contrast),
                ("Гама:", self.gamma), ("Фільтр:", self.filter)]
        for i, (t, w) in enumerate(rows):
            tone.addWidget(QLabel(t), i, 0)
            tone.addWidget(w, i, 1)
        tone.addWidget(self.auto_levels, len(rows), 0, 1, 2)

        lay = QVBoxLayout(self)
        lay.addWidget(self.btn_auto)
        lay.addWidget(self.btn_format)
        lay.addLayout(geo)
        lay.addLayout(tone)
        bottom = QHBoxLayout()
        bottom.addWidget(btn("Скинути все", "reset"))
        bottom.addWidget(btn("Застосувати до всіх", "apply_all", "Тон і фільтр цієї сторінки — для всього пакета"))
        lay.addLayout(bottom)
        bottom = QHBoxLayout()
        bottom.addWidget(btn("Автоформат усього пакета", "autoformat_all",
                             "Поворот, вирівнювання й обрізання всіх сторінок (паралельно)"))
        lay.addLayout(bottom)

        # Повзунки оновлюють прев'ю з невеликою затримкою, щоб не гальмувати
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(lambda: self.adjust_changed.emit(self._adj))

    def load(self, adj: Adjust | None) -> None:
        self.setEnabled(adj is not None)
        if adj is None:
            return
        self._loading = True
        self._adj = adj
        self.angle.setValue(adj.fine_angle)
        self.brightness.set_value(adj.brightness)
        self.contrast.set_value(adj.contrast)
        self.gamma.set_value(adj.gamma)
        self.auto_levels.setChecked(adj.auto_levels)
        self.filter.setCurrentIndex(max(0, self.filter.findData(adj.filter)))
        self._loading = False

    def _emit(self) -> None:
        if self._loading:
            return
        a = self._adj
        if abs(a.fine_angle - self.angle.value()) > 1e-6:
            a.crop = None        # після зміни кута стара рамка вже не відповідає
        a.fine_angle = self.angle.value()
        a.brightness = int(self.brightness.value())
        a.contrast = int(self.contrast.value())
        a.gamma = float(self.gamma.value())
        a.auto_levels = self.auto_levels.isChecked()
        a.filter = self.filter.currentData()
        self._timer.start()
