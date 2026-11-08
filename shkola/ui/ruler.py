"""Горизонтальна лінійка над аркушем InterText (см): береги сторінки сірі, робоча область біла,
маркери відступу абзацу (перший рядок ▽, лівий △) можна тягнути мишею."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from . import theme

CM = 96 / 2.54


class Ruler(QWidget):
    indents_changed = Signal(float, float)       # (перший рядок px, лівий відступ px)

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(22)
        self.page_x = 0            # лівий край аркуша у координатах лінійки
        self.page_w = 794
        self.left = 113            # береги, px
        self.right = 38
        self.first = 0.0           # відступ першого рядка, px
        self.indent = 0.0          # лівий відступ абзацу, px
        self._drag = None
        self.setMouseTracking(True)

    def set_page(self, page_x: int, page_w: int, left: int, right: int) -> None:
        self.page_x, self.page_w, self.left, self.right = page_x, page_w, left, right
        self.update()

    def set_indents(self, first: float, indent: float) -> None:
        self.first, self.indent = first, indent
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#e7ebe9"))
        x0 = self.page_x + self.left
        x1 = self.page_x + self.page_w - self.right
        p.fillRect(QRectF(self.page_x, 4, self.page_w, 14), QColor("#d3d9d6"))
        p.fillRect(QRectF(x0, 4, x1 - x0, 14), QColor("white"))
        p.setPen(QPen(QColor(theme.MUTED), 1))
        f = p.font()
        f.setPointSize(7)
        p.setFont(f)
        n = 0
        x = x0
        while x <= self.page_x + self.page_w:
            p.drawLine(int(x), 14, int(x), 18)
            if n and x < x1 + 1:
                p.drawText(int(x) - 8, 2, 16, 12, Qt.AlignmentFlag.AlignCenter, str(n))
            if x + CM / 2 <= x1:
                p.drawLine(int(x + CM / 2), 16, int(x + CM / 2), 18)
            x += CM
            n += 1
        x = x0 - CM
        while x >= self.page_x:
            p.drawLine(int(x), 14, int(x), 18)
            x -= CM
        # маркери відступів
        p.setPen(QPen(QColor(theme.PRIMARY_DARK), 1))
        p.setBrush(QColor(theme.PRIMARY))
        fx = x0 + self.indent + self.first
        p.drawPolygon(QPolygonF([QPointF(fx - 5, 3), QPointF(fx + 5, 3), QPointF(fx, 9)]))
        ix = x0 + self.indent
        p.drawPolygon(QPolygonF([QPointF(ix - 5, 19), QPointF(ix + 5, 19), QPointF(ix, 13)]))
        p.end()

    def _hit(self, pos) -> str | None:
        x0 = self.page_x + self.left
        if abs(pos.x() - (x0 + self.indent + self.first)) <= 6 and pos.y() < 11:
            return "first"
        if abs(pos.x() - (x0 + self.indent)) <= 6 and pos.y() >= 11:
            return "indent"
        return None

    def mousePressEvent(self, e) -> None:
        self._drag = self._hit(e.position())

    def mouseMoveEvent(self, e) -> None:
        if not self._drag:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._hit(e.position()) else Qt.CursorShape.ArrowCursor)
            return
        x0 = self.page_x + self.left
        v = max(0.0, min(e.position().x() - x0, self.page_w - self.left - self.right - 20))
        if self._drag == "first":
            self.first = v - self.indent
        else:
            self.indent = v
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            self._drag = None
            self.indents_changed.emit(self.first, self.indent)
