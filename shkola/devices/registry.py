"""Об'єднує бекенди: пошук пристроїв, перевірка зв'язку, вибір бекенда для сканування."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from ..core.models import Link, ScannerInfo
from .base import ScannerBackend
from .escl_backend import EsclBackend
from .wia_backend import WiaBackend

log = logging.getLogger(__name__)


class DeviceRegistry:
    def __init__(self, manual_hosts: list[str]) -> None:
        self.escl = EsclBackend(manual_hosts)
        self.backends: dict[str, ScannerBackend] = {"wia": WiaBackend(), "escl": self.escl}

    def set_manual_hosts(self, hosts: list[str]) -> None:
        self.escl.manual_hosts = list(hosts)

    def backend(self, info: ScannerInfo) -> ScannerBackend:
        return self.backends[info.backend]

    def discover_and_check(self, network_scan: bool = False, progress=None) -> list[ScannerInfo]:
        """Знайти всі пристрої та перевірити зв'язок з кожним ДО показу списку.
        network_scan=True — ще й перебрати адреси локальних підмереж."""
        if network_scan:
            from .subnet_scan import scan_networks
            self.escl.found_hosts = scan_networks(progress=progress)
        devices: list[ScannerInfo] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result in pool.map(self._safe_discover, self.backends.values()):
                devices.extend(result)
        # WIA працює з COM — перевіряємо послідовно; мережні eSCL — паралельно
        wia = [d for d in devices if d.backend == "wia"]
        net = [d for d in devices if d.backend != "wia"]
        for d in wia:
            self.check(d)
        if net:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(self.check, net))
        order = {Link.ONLINE: 0, Link.BUSY: 1, Link.UNKNOWN: 2, Link.OFFLINE: 3}
        return sorted(devices, key=lambda d: (order[d.link], d.name.lower()))

    def check(self, info: ScannerInfo) -> ScannerInfo:
        try:
            info.link, info.link_detail = self.backend(info).check_link(info)
        except Exception as e:
            log.exception("Перевірка зв'язку %s", info.key)
            info.link, info.link_detail = Link.OFFLINE, str(e)
        return info

    @staticmethod
    def _safe_discover(backend: ScannerBackend) -> list[ScannerInfo]:
        try:
            return backend.discover()
        except Exception:
            log.exception("Пошук у бекенді %s", backend.name)
            return []
