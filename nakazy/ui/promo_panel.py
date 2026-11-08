"""Панель «Курси УАІТ» у головному вікні: картка зі «Сканера» + кеш свіжих даних (nakazy/promo.py)."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from shkola.ui import promo_panel as base

from .. import promo


class _Fetch(QThread):
    done = Signal(dict)

    def __init__(self, current: dict):
        super().__init__()
        self.current = current

    def run(self):
        new = promo.refresh(self.current)
        if new:
            self.done.emit(new)


class PromoPanel(base.PromoPanel):
    def __init__(self, online: bool = True):
        super().__init__(online=False)       # без власного запиту базового класу
        self.data = promo.load_offline()      # кеш свіжого або вшите
        self.show_course(0)
        if online:
            self._fetch = _Fetch(self.data)
            self._fetch.done.connect(self._update)
            self._fetch.start()
