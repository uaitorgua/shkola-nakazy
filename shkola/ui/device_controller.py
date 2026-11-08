"""Пошук пристроїв і перевірка зв'язку перед показом списку."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from ..devices.registry import DeviceRegistry
from .device_panel import DevicePanel
from .scan_panel import ScanPanel
from .workers import DiscoverWorker


class DeviceController(QObject):
    def __init__(self, registry: DeviceRegistry, panel: DevicePanel, scan_panel: ScanPanel, store) -> None:
        super().__init__()
        self.registry, self.panel, self.scan_panel, self.store = registry, panel, scan_panel, store
        self._worker: DiscoverWorker | None = None
        panel.refresh_requested.connect(self.refresh)
        panel.recheck_requested.connect(self.recheck)
        panel.host_added.connect(self._add_host)
        panel.selection_changed.connect(self._selected)
        panel.netscan_requested.connect(lambda: self.refresh(network_scan=True))
        self.timer = QTimer(self)
        self.timer.setInterval(30_000)
        self.timer.timeout.connect(self._auto_recheck)
        self.timer.start()

    def busy(self) -> bool:
        return bool(self._worker and self._worker.isRunning())

    def refresh(self, network_scan: bool = False) -> None:
        if self.busy():
            return
        if self.scan_busy():
            self.panel.status.setText("Зачекайте, триває сканування документа…")
            return
        self.panel.set_busy(True, "Сканую мережу…" if network_scan else "Шукаю сканери та перевіряю зв'язок…")
        self.panel.set_devices([])
        self._worker = DiscoverWorker(self.registry, network_scan=network_scan)
        self._worker.progress.connect(lambda a, b: self.panel.status.setText(f"Сканую мережу: {a} з {b} адрес…"))
        self._worker.done.connect(self._found)
        self._worker.failed.connect(lambda m: self.panel.set_busy(False, f"Помилка пошуку: {m}"))
        self._worker.start()

    def recheck(self, info) -> None:
        if (self._worker and self._worker.isRunning()) or self.scan_busy():
            return
        self.panel.set_busy(True, f"Перевіряю зв'язок із {info.name}…")
        self._worker = DiscoverWorker(self.registry, only=info)
        self._worker.done.connect(lambda lst: (self.panel.set_busy(False), self.panel.update_device(lst[0])))
        self._worker.failed.connect(lambda m: self.panel.set_busy(False, m))
        self._worker.start()

    def _auto_recheck(self) -> None:
        """Тихо оновлює кольорові значки зв'язку (не під час сканування документа)."""
        if not self.panel.auto.isChecked() or self.busy() or not self.panel.devices or self.scan_busy():
            return
        self._worker = DiscoverWorker(self.registry, devices=list(self.panel.devices))
        self._worker.done.connect(self.panel.update_links)
        self._worker.start()

    scan_busy = staticmethod(lambda: False)     # підміняється головним вікном

    def _found(self, devices) -> None:
        self.panel.set_busy(False)
        self.panel.set_devices(devices, self.store.get("last_scanner"))

    def _add_host(self, host: str) -> None:
        hosts = list(self.store.get("manual_hosts"))
        if host not in hosts:
            hosts.append(host)
            self.store.set("manual_hosts", hosts)
        self.registry.set_manual_hosts(hosts)
        self.refresh()

    def _selected(self, info) -> None:
        self.scan_panel.set_device(info)
        if info:
            self.store.set("last_scanner", info.key)
