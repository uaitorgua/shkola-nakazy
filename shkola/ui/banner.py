"""Шапка вікна: логотип, назва програми, підпис. Зелено-графітовий градієнт малюється вручну."""

from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..config import APP_NAME
from . import theme
from .logo import logo_pixmap


class Banner(QWidget):
    """Шапка головного вікна; title/subtitle/compact — для субдодатків InterText та InterTab."""

    def __init__(self, title: str = APP_NAME, subtitle: str = "СКАНУВАННЯ · РОЗПІЗНАВАННЯ ТЕКСТУ Й ФОРМУЛ · "
                 "РЕДАКТОР ДОКУМЕНТІВ І ТАБЛИЦЬ", compact: bool = False) -> None:
        super().__init__()
        self.setFixedHeight(44 if compact else 64)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(30 if compact else 48))
        title_l = QLabel(title)
        title_l.setStyleSheet(f"color: #ffffff; font-size: {12 if compact else 15}pt; font-weight: 700; background: transparent;")
        title = title_l
        sub = QLabel(subtitle)
        sub.setStyleSheet(f"color: {theme.ACCENT}; font-size: 8.5pt; font-weight: 700; "
                          "letter-spacing: 1px; background: transparent;")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(title)
        text.addWidget(sub)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 2 if compact else 6, 14, 6 if compact else 10)
        lay.setSpacing(12)
        lay.addWidget(logo)
        lay.addLayout(text, 1)
        if compact:
            right = QLabel(APP_NAME)
            right.setStyleSheet("color: #cfe3dc; font-size: 9pt; background: transparent;")
            lay.addWidget(right)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor(theme.GRAPHITE))
        g.setColorAt(1, QColor(theme.PRIMARY_DARK))
        p.fillRect(self.rect(), g)
        p.fillRect(0, self.height() - 4, self.width(), 4, QColor(theme.ACCENT))
        p.end()
