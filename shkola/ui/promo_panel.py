"""Панель «Курси УАІТ»: гарна картка-карусель у головному вікні. Дані — promo/courses.json (у збірці)
з оновленням онлайн із uait.org.ua у фоні (без блокування; без інтернету показує вбудований перелік).
Кнопка «Записатися» відкриває сторінку курсу в браузері, «Усі курси» — JS-сторінку promo/index.html."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..config import resource_dir
from . import theme

log = logging.getLogger(__name__)
LOCAL_JSON = resource_dir() / "promo" / "courses.json"
ONLINE_JSON = "https://uait.org.ua/skaner/courses.json"
ALL_COURSES_URL = "https://uait.org.ua/skaner/"
ROTATE_MS = 9000


def load_local() -> dict:
    try:
        return json.loads(LOCAL_JSON.read_text(encoding="utf-8"))
    except Exception:
        log.exception("promo/courses.json")
        return {"courses": []}


class _Fetch(QThread):
    done = Signal(dict)

    def run(self) -> None:
        try:
            import requests
            r = requests.get(ONLINE_JSON, timeout=6)
            if r.ok and r.json().get("courses"):
                self.done.emit(r.json())
        except Exception:
            pass


class PromoPanel(QWidget):
    def __init__(self, online: bool = True) -> None:
        super().__init__()
        self.setObjectName("promo")
        self.setFixedHeight(190)
        self.data = load_local()
        self.i = 0
        self.color = QColor(theme.PRIMARY)

        self.kicker = QLabel("КУРСИ УАІТ · ДЛЯ ВЧИТЕЛІВ ТА УЧНІВ")
        self.kicker.setStyleSheet(f"color: {theme.ACCENT}; font-size: 8pt; font-weight: 800; letter-spacing: 1px; background: transparent;")
        self.name = QLabel("")
        self.name.setStyleSheet("color: white; font-size: 13pt; font-weight: 800; background: transparent;")
        self.name.setWordWrap(True)
        self.short = QLabel("")
        self.short.setStyleSheet("color: #e9f2ee; font-size: 9.5pt; background: transparent;")
        self.short.setWordWrap(True)
        self.meta = QLabel("")
        self.meta.setStyleSheet("color: #cfe3dc; font-size: 8.5pt; background: transparent;")
        self.meta.setWordWrap(True)
        self.btn = QPushButton("Записатися")
        self.btn.setObjectName("accent")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self._open)
        self.all = QPushButton("Усі курси")
        self.all.setStyleSheet("QPushButton { background: rgba(255,255,255,0.14); color: white; border: 1px solid rgba(255,255,255,0.4); }"
                               "QPushButton:hover { background: rgba(255,255,255,0.26); }")
        self.all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ALL_COURSES_URL)))
        self.prev = QPushButton("‹")
        self.next = QPushButton("›")
        for b in (self.prev, self.next):
            b.setFixedSize(26, 26)
            b.setStyleSheet("QPushButton { background: rgba(255,255,255,0.14); color: white; border: none; border-radius: 13px; font-weight: 800; }"
                            "QPushButton:hover { background: rgba(255,255,255,0.3); }")
        self.prev.clicked.connect(lambda: self.show_course(self.i - 1))
        self.next.clicked.connect(lambda: self.show_course(self.i + 1))
        self.dots = QLabel("")
        self.dots.setStyleSheet("color: white; background: transparent; font-size: 9pt;")

        top = QHBoxLayout()
        top.addWidget(self.kicker, 1)
        top.addWidget(self.prev)
        top.addWidget(self.dots)
        top.addWidget(self.next)
        bottom = QHBoxLayout()
        bottom.addWidget(self.btn)
        bottom.addWidget(self.all)
        bottom.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addWidget(self.name)
        lay.addWidget(self.short)
        lay.addWidget(self.meta)
        lay.addStretch(1)
        lay.addLayout(bottom)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.show_course(self.i + 1))
        self.timer.start(ROTATE_MS)
        self.show_course(0)
        self._fetch = None
        if online:
            self._fetch = _Fetch()
            self._fetch.done.connect(self._update)
            self._fetch.start()

    def courses(self) -> list[dict]:
        return self.data.get("courses") or []

    def _update(self, data: dict) -> None:
        self.data = data
        self.show_course(0)

    def show_course(self, i: int) -> None:
        cs = self.courses()
        if not cs:
            self.name.setText("Курси УАІТ")
            self.short.setText("Онлайн-курси для вчителів та учнів — uait.org.ua")
            return
        self.i = i % len(cs)
        c = cs[self.i]
        self.name.setText(c.get("name", ""))
        self.short.setText(c.get("short", ""))
        self.meta.setText(" · ".join(x for x in (c.get("audience"), c.get("format"), c.get("price")) if x))
        self.color = QColor(c.get("color") or theme.PRIMARY)
        self.dots.setText(" ".join("●" if k == self.i else "○" for k in range(len(cs))))
        self.update()

    def _open(self) -> None:
        cs = self.courses()
        if cs:
            QDesktopServices.openUrl(QUrl(cs[self.i].get("url") or ALL_COURSES_URL))

    def enterEvent(self, e) -> None:
        self.timer.stop()

    def leaveEvent(self, e) -> None:
        self.timer.start(ROTATE_MS)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, self.color.darker(130))
        g.setColorAt(1, self.color)
        p.fillPath(path, g)
        p.setPen(QColor(theme.ACCENT))
        p.drawPath(path)
        p.end()
