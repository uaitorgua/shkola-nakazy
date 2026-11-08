"""Логотип «Сканер ШКОЛА» (варіант Б родини УАІТ: аркуш і бірюзовий промінь).

assets/logo.svg — повний малюнок (32 px і більше), assets/logo_small.svg — спрощений для 16–24 px
(товщі елементи, без деталей), щоб іконка лишалась читабельною в панелі задач і Провіднику.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..config import ASSETS, LOGO_PNG, LOGO_SVG

LOGO_SMALL_SVG = ASSETS / "logo_small.svg"
SMALL_MAX = 24


def logo_pixmap(size: int) -> QPixmap:
    if LOGO_PNG.exists():
        pm = QPixmap(str(LOGO_PNG))
        return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    src = LOGO_SMALL_SVG if size <= SMALL_MAX and LOGO_SMALL_SVG.exists() else LOGO_SVG
    if src.exists():
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(str(src)).render(p)
        p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon
