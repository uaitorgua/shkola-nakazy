"""Панель пристроїв: випадаючий список сканерів зі станом зв'язку, пошук і ручне додавання."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QPushButton, QToolButton, QVBoxLayout)

from ..core.models import Link, ScannerInfo
from . import theme

_COLORS = {Link.ONLINE: theme.OK, Link.BUSY: theme.WARN, Link.OFFLINE: theme.BAD, Link.UNKNOWN: theme.MUTED}


def _dot(color: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pm)


class DevicePanel(QGroupBox):
    refresh_requested = Signal()
    recheck_requested = Signal(object)      # ScannerInfo
    selection_changed = Signal(object)      # ScannerInfo | None
    host_added = Signal(str)
    netscan_requested = Signal()

    def __init__(self) -> None:
        super().__init__("1 · Сканер")
        self.devices: list[ScannerInfo] = []
        self.combo = QComboBox()
        self.combo.setMinimumContentsLength(12)
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.currentIndexChanged.connect(self._on_row)

        self.btn_find = QPushButton("⟳ Оновити")
        self.btn_find.setToolTip("Знайти сканери та перевірити зв'язок")
        self.btn_find.clicked.connect(self.refresh_requested)

        # Рідше потрібне — у меню
        self.btn_more = QToolButton()
        self.btn_more.setText("Пошук ▾")
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_more)
        for text, slot in (("Перевірити зв'язок із вибраним", self._recheck),
                           ("Сканувати мережу (усі адреси підмережі)", self.netscan_requested.emit),
                           ("Додати мережний сканер за IP…", self._add_host)):
            a = QAction(text, menu)
            a.triggered.connect(slot)
            menu.addAction(a)
        menu.addSeparator()
        self.auto_action = QAction("Оновлювати стан кожні 30 с", menu, checkable=True, checked=True)
        menu.addAction(self.auto_action)
        self.btn_more.setMenu(menu)
        self.auto = _ActionCheck(self.auto_action)     # сумісність: .isChecked()

        self.status = QLabel("Перевіряю сканери…")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(40)          # два рядки підказки, без обрізання

        row = QHBoxLayout()
        row.addWidget(self.combo, 1)
        row.addWidget(self.btn_find)
        row.addWidget(self.btn_more)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.status)

    # для сумісності з тестами/контролером
    @property
    def list(self):
        return _ComboAsList(self.combo)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.btn_find.setEnabled(not busy)
        self.btn_more.setEnabled(not busy)
        if text:
            self.status.setText(text)

    def set_devices(self, devices: list[ScannerInfo], select_key: str = "") -> None:
        self.devices = devices
        self.combo.blockSignals(True)
        self.combo.clear()
        row_to_select = 0
        for i, d in enumerate(devices):
            self.combo.addItem(_dot(_COLORS[d.link]), d.label)
            self.combo.setItemData(i, f"{d.link.value}: {d.link_detail}", Qt.ItemDataRole.ToolTipRole)
            if d.key == select_key:
                row_to_select = i
        if not devices:
            self.combo.addItem("— сканерів не знайдено —")
        self.combo.blockSignals(False)
        online = sum(d.link == Link.ONLINE for d in devices)
        self.status.setText(f"Знайдено: {len(devices)}, на зв'язку: {online}" if devices
                            else "Перевірте живлення/кабель/мережу, «Пошук ▾ → Сканувати мережу» або додайте IP.")
        if devices:
            self.combo.setCurrentIndex(row_to_select)
            self._on_row(row_to_select)
        else:
            self.selection_changed.emit(None)

    def update_device(self, info: ScannerInfo) -> None:
        self.update_links([info])
        self.status.setText(f"{info.name}: {info.link.value} — {info.link_detail}")
        self.selection_changed.emit(self.current())

    def update_links(self, devices: list[ScannerInfo]) -> None:
        """Оновити лише значки стану, не чіпаючи вибір."""
        for d in devices:
            for i, old in enumerate(self.devices):
                if old.key == d.key:
                    self.devices[i] = d
                    self.combo.setItemIcon(i, _dot(_COLORS[d.link]))
                    self.combo.setItemText(i, d.label)
                    self.combo.setItemData(i, f"{d.link.value}: {d.link_detail}", Qt.ItemDataRole.ToolTipRole)

    def current(self) -> ScannerInfo | None:
        r = self.combo.currentIndex()
        return self.devices[r] if 0 <= r < len(self.devices) else None

    def _on_row(self, _row: int) -> None:
        d = self.current()
        if d:
            self.status.setText(f"{d.link.value} — {d.link_detail}")
        self.selection_changed.emit(d)

    def _recheck(self) -> None:
        if self.current():
            self.recheck_requested.emit(self.current())

    def _add_host(self) -> None:
        text, ok = QInputDialog.getText(self, "Мережний сканер",
                                        "IP-адреса або ім'я вузла (за потреби з портом, напр. 192.168.1.50:8080):")
        if ok and text.strip():
            self.host_added.emit(text.strip())


class _ActionCheck:
    def __init__(self, action: QAction) -> None:
        self.action = action

    def isChecked(self) -> bool:
        return self.action.isChecked()


class _ComboAsList:
    def __init__(self, combo: QComboBox) -> None:
        self.combo = combo

    def setCurrentRow(self, row: int) -> None:
        self.combo.setCurrentIndex(row)

    def currentRow(self) -> int:
        return self.combo.currentIndex()
