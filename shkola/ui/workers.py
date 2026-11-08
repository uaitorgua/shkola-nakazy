"""Фонові потоки: пошук/перевірка пристроїв, сканування, експорт. Інтерфейс не зависає."""

from __future__ import annotations

import logging
import time
import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal

from ..core.models import Page, ScannerInfo, ScanSettings
from ..devices.base import ScanCancelled
from ..devices.registry import DeviceRegistry
from ..imaging import parallel, pipeline

log = logging.getLogger(__name__)

BUSY_WAIT_S = 60   # скільки чекати, поки зайнятий сканер звільниться


class DiscoverWorker(QThread):
    done = Signal(list)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, registry: DeviceRegistry, only: ScannerInfo | None = None,
                 network_scan: bool = False, devices: list | None = None) -> None:
        super().__init__()
        self.registry, self.only, self.network_scan, self.devices = registry, only, network_scan, devices

    def run(self) -> None:
        try:
            if self.only:
                self.done.emit([self.registry.check(self.only)])
            elif self.devices is not None:          # тихе оновлення стану вже знайдених
                self.done.emit([self.registry.check(d) for d in self.devices])
            else:
                self.done.emit(self.registry.discover_and_check(
                    self.network_scan, lambda a, b: self.progress.emit(a, b)))
        except Exception as e:
            log.exception("Пошук пристроїв")
            self.failed.emit(str(e))


class ScanWorker(QThread):
    page_ready = Signal(object)        # Page
    finished_ok = Signal(int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, registry: DeviceRegistry, info: ScannerInfo, settings: ScanSettings, auto: dict) -> None:
        super().__init__()
        self.registry, self.info, self.settings, self.auto = registry, info, settings, auto
        self.cancel_event = threading.Event()
        self._pending: list = []

    def cancel(self) -> None:
        self.cancel_event.set()

    def _on_image(self, img) -> None:
        # сканер не чекає на обробку: наступний аркуш тягнеться, поки цей вирівнюється в іншому потоці
        self._pending.append(parallel.pool().submit(self._process, img))
        self._flush(block=False)

    def _flush(self, block: bool) -> None:
        while self._pending and (block or self._pending[0].done()):
            self.page_ready.emit(self._pending.pop(0).result())

    def _process(self, img) -> Page:
        page = Page(original=img, dpi=self.settings.dpi)
        try:
            if self.auto.get("autoformat"):
                pipeline.auto_format(page)
            if self.auto.get("auto_levels"):
                page.adjust.auto_levels = True
        except Exception:
            log.exception("Автообробка сторінки")
        return page

    def run(self) -> None:
        try:
            # Сканування не починається, доки сканер не готовий: перевіряємо зв'язок
            # безпосередньо перед стартом; якщо зайнятий — чекаємо до BUSY_WAIT_S.
            from ..core.models import Link
            deadline = time.monotonic() + BUSY_WAIT_S
            while True:
                self.registry.check(self.info)
                if self.info.link == Link.OFFLINE:
                    self.failed.emit(f"Немає зв'язку зі сканером: {self.info.link_detail}")
                    return
                if self.info.link != Link.BUSY or time.monotonic() > deadline:
                    break
                if self.cancel_event.wait(2):
                    raise ScanCancelled()
            if self.info.link == Link.BUSY:
                self.failed.emit(f"Сканер зайнятий: {self.info.link_detail}. Спробуйте пізніше.")
                return
            n = self.registry.backend(self.info).scan(self.info, self.settings, self._on_image, self.cancel_event)
            self._flush(block=True)
            self.finished_ok.emit(n)
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as e:
            log.exception("Сканування")
            self.failed.emit(str(e))


class TaskWorker(QThread):
    """Довільна довга дія з прогресом (експорт)."""
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, *args) -> None:
        super().__init__()
        self.fn, self.args = fn, args

    def run(self) -> None:
        try:
            self.done.emit(self.fn(*self.args, progress=lambda a, b: self.progress.emit(a, b)))
        except Exception as e:
            log.exception("Фонове завдання")
            self.failed.emit(str(e))
