"""Спільний інтерфейс бекендів сканування."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Callable

from PIL import Image

from ..core.models import Link, ScannerInfo, ScanSettings


class ScanCancelled(Exception):
    pass


class ScanError(Exception):
    pass


# Колбек отримує кожну відскановану сторінку одразу (сторінки з'являються «наживо»)
PageCallback = Callable[[Image.Image], None]


class ScannerBackend(ABC):
    name: str = ""

    @abstractmethod
    def discover(self) -> list[ScannerInfo]:
        """Знайти пристрої (без перевірки зв'язку)."""

    @abstractmethod
    def check_link(self, info: ScannerInfo) -> tuple[Link, str]:
        """Перевірити зв'язок із пристроєм: (стан, пояснення)."""

    @abstractmethod
    def scan(self, info: ScannerInfo, settings: ScanSettings,
             on_page: PageCallback, cancel: threading.Event) -> int:
        """Сканувати; повертає кількість сторінок."""
