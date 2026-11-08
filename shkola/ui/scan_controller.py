"""Запуск сканування, одиночний/пакетний режим, продовження з планшета."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from ..core.models import Link, ScanMode, Source
from ..devices.registry import DeviceRegistry
from .device_panel import DevicePanel
from .page_controller import PageController
from .scan_panel import InsertAt, ScanPanel
from .workers import ScanWorker


class ScanController(QObject):
    status = Signal(str)

    def __init__(self, parent: QWidget, registry: DeviceRegistry, devices: DevicePanel,
                 panel: ScanPanel, pages: PageController) -> None:
        super().__init__(parent)
        self.win, self.registry, self.devices, self.panel, self.pages = parent, registry, devices, panel, pages
        self._worker: ScanWorker | None = None
        self._starting = False      # захист від подвійного кліку, поки відкриті діалоги перед стартом
        self._got = 0
        panel.scan_requested.connect(self.start)
        panel.cancel_requested.connect(self.cancel)

    def busy(self) -> bool:
        return self._starting or bool(self._worker and self._worker.isRunning())

    def start(self, continuing: bool = False) -> None:
        info = self.devices.current()
        if not info or self.busy():
            return
        self._starting = True
        self.panel.set_scanning(True)       # кнопка гасне одразу, ще до діалогів
        try:
            self._start(info, continuing)
        finally:
            self._starting = False
            if not (self._worker and self._worker.isRunning()):
                self.panel.set_scanning(False)

    def _start(self, info, continuing: bool) -> None:
        if info.link == Link.OFFLINE and QMessageBox.question(
                self.win, "Немає зв'язку",
                f"{info.name}: {info.link_detail}.\nСпробувати все одно?") != QMessageBox.StandardButton.Yes:
            return
        mode = self.panel.mode()
        if not continuing:
            if mode == ScanMode.SINGLE and len(self.pages.batch) and QMessageBox.question(
                    self.win, "Новий документ",
                    "Поточний пакет буде очищено. Продовжити?") != QMessageBox.StandardButton.Yes:
                return
            self.pages.begin_insert(self.panel.insert_at(), single_mode=mode == ScanMode.SINGLE)
        self._got = 0
        self.panel.set_scanning(True)
        self.status.emit(f"Сканую на {info.name}…")
        self._worker = ScanWorker(self.registry, info, self.panel.settings(), self.panel.auto())
        self._worker.page_ready.connect(self._page)
        self._worker.finished_ok.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.cancelled.connect(lambda: self._end("Сканування скасовано"))
        self._worker.start()

    def cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status.emit("Скасовую…")

    def _page(self, page) -> None:
        self._got += 1
        self.pages.add_page(page)
        self.status.emit(f"Отримано сторінок: {self._got}")

    def _done(self, n: int) -> None:
        self._end(f"Готово: відскановано сторінок — {n}. У пакеті: {len(self.pages.batch)}")
        s = self.panel.settings()
        if self.panel.mode() == ScanMode.BATCH and s.source == Source.FLATBED:
            # для заміни наступні сторінки вже йдуть «після»
            if self.panel.insert_at() == InsertAt.REPLACE:
                self.panel.cb_insert.setCurrentText(InsertAt.AFTER.value)
            box = QMessageBox(QMessageBox.Icon.Question, "Пакет",
                              "Покладіть наступний аркуш на скло сканера.", parent=self.win)
            nxt = box.addButton("Сканувати наступну", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Завершити пакет", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is nxt:
                self.start(continuing=True)

    def _failed(self, msg: str) -> None:
        self._end(f"Помилка: {msg}")
        QMessageBox.warning(self.win, "Помилка сканування", msg)

    def _end(self, msg: str) -> None:
        self.panel.set_scanning(False)
        self.status.emit(msg)
