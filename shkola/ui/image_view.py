"""Перегляд сторінки: масштаб колесом, панорамування, інструмент кадрування рамкою з ручками."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from . import theme

HANDLE = 10


ZOOM_MIN, ZOOM_MAX = 0.05, 8.0


class ImageView(QGraphicsView):
    crop_changed = Signal(object)      # (x0, y0, x1, y1) у координатах зображення-прев'ю або None
    zoom_changed = Signal(float)       # поточний масштаб (1.0 = 100 %)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor(theme.VIEW_BG))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.pix = QGraphicsPixmapItem()
        self.scene().addItem(self.pix)
        self.shade = QGraphicsPathItem()
        self.shade.setBrush(QBrush(QColor(0, 0, 0, 120)))
        self.shade.setPen(Qt.PenStyle.NoPen)
        self.frame = QGraphicsRectItem()
        self.frame.setPen(QPen(QColor(theme.GOLD), 0, Qt.PenStyle.DashLine))
        for it in (self.shade, self.frame):
            it.setZValue(1)
            it.setVisible(False)
            self.scene().addItem(it)
        self.crop_mode = False
        self._rect: QRectF | None = None
        self._drag: str | None = None
        self._anchor = QPointF()
        self._fit = True
        self._pan_last = None          # панорамування середньою/правою кнопкою в будь-якому режимі

    # ---------- масштаб ----------
    def zoom_factor(self) -> float:
        return self.transform().m11()

    def set_zoom(self, z: float) -> None:
        """Встановити масштаб (1.0 = 100 %) із центром у середині вікна."""
        z = min(max(z, ZOOM_MIN), ZOOM_MAX)
        self._fit = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.resetTransform()
        self.scale(z, z)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoom_changed.emit(z)

    def zoom_100(self) -> None:
        self.set_zoom(1.0)

    # ---------- зображення ----------
    def set_pixmap(self, pm: QPixmap | None, crop: tuple | None = None, keep_view: bool = False) -> None:
        self.pix.setPixmap(pm or QPixmap())
        self.viewport().update()
        self.scene().setSceneRect(QRectF(self.pix.pixmap().rect()))
        self._rect = QRectF(QPointF(crop[0], crop[1]), QPointF(crop[2], crop[3])) if crop else None
        self._update_overlay()
        if not keep_view or self._fit:
            self.fit()

    def drawForeground(self, painter, rect) -> None:
        if not self.pix.pixmap().isNull():
            return
        painter.save()
        painter.resetTransform()
        vr = self.viewport().rect()
        painter.setPen(QColor(theme.GOLD))
        f = painter.font()
        f.setPointSize(16)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(vr.adjusted(0, -40, 0, -40), Qt.AlignmentFlag.AlignCenter, "Пакет порожній")
        f.setPointSize(10)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(QColor("#c3cbdb"))
        painter.drawText(vr.adjusted(16, 30, -16, 30), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         "Оберіть сканер ліворуч і натисніть «Сканувати» (F5)\n"
                         "або додайте PDF / зображення (Ctrl+O), чи перетягніть файли сюди")
        painter.restore()

    def fit(self) -> None:
        self._fit = True
        if not self.pix.pixmap().isNull():
            self.fitInView(self.pix, Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(self.zoom_factor())

    def zoom(self, factor: float) -> None:
        z = self.zoom_factor() * factor
        if z < ZOOM_MIN or z > ZOOM_MAX:
            return
        self._fit = False
        self.scale(factor, factor)
        self.zoom_changed.emit(self.zoom_factor())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self._fit:
            self.fit()

    def wheelEvent(self, e) -> None:
        self.zoom(1.25 if e.angleDelta().y() > 0 else 0.8)

    # ---------- кадрування ----------
    def set_crop_mode(self, on: bool) -> None:
        self.crop_mode = on
        self.setDragMode(QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.ScrollHandDrag)
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        self._update_overlay()

    def _hit(self, p: QPointF) -> str | None:
        if not self._rect:
            return None
        tol = HANDLE / max(self.transform().m11(), 1e-3)
        r = self._rect
        near = lambda a, b: abs(a - b) <= tol
        h = ""
        if near(p.y(), r.top()):
            h += "t"
        elif near(p.y(), r.bottom()):
            h += "b"
        if near(p.x(), r.left()):
            h += "l"
        elif near(p.x(), r.right()):
            h += "r"
        if h:
            return h
        return "move" if r.contains(p) else None

    def mousePressEvent(self, e) -> None:
        if e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_last = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self.crop_mode or e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        p = self._clamp(self.mapToScene(e.position().toPoint()))
        self._drag = self._hit(p) or "new"
        self._anchor = p
        if self._drag == "new":
            self._rect = QRectF(p, p)
        self._start = QRectF(self._rect) if self._rect else None

    def mouseMoveEvent(self, e) -> None:
        if self._pan_last is not None:
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if not self.crop_mode:
            return super().mouseMoveEvent(e)
        p = self._clamp(self.mapToScene(e.position().toPoint()))
        if not self._drag:
            hit = self._hit(p)
            cursors = {"move": Qt.CursorShape.SizeAllCursor, "t": Qt.CursorShape.SizeVerCursor,
                       "b": Qt.CursorShape.SizeVerCursor, "l": Qt.CursorShape.SizeHorCursor,
                       "r": Qt.CursorShape.SizeHorCursor, "tl": Qt.CursorShape.SizeFDiagCursor,
                       "br": Qt.CursorShape.SizeFDiagCursor, "tr": Qt.CursorShape.SizeBDiagCursor,
                       "bl": Qt.CursorShape.SizeBDiagCursor}
            self.setCursor(cursors.get(hit, Qt.CursorShape.CrossCursor))
            return
        r = QRectF(self._start) if self._start else QRectF()
        if self._drag == "new":
            r = QRectF(self._anchor, p).normalized()
        elif self._drag == "move":
            d = p - self._anchor
            r.translate(d)
            bounds = self.scene().sceneRect()
            r.moveLeft(min(max(r.left(), 0), bounds.width() - r.width()))
            r.moveTop(min(max(r.top(), 0), bounds.height() - r.height()))
        else:
            if "t" in self._drag:
                r.setTop(p.y())
            if "b" in self._drag:
                r.setBottom(p.y())
            if "l" in self._drag:
                r.setLeft(p.x())
            if "r" in self._drag:
                r.setRight(p.x())
            r = r.normalized()
        self._rect = r
        self._update_overlay()

    def mouseReleaseEvent(self, e) -> None:
        if self._pan_last is not None and e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_last = None
            self.setCursor(Qt.CursorShape.CrossCursor if self.crop_mode else Qt.CursorShape.ArrowCursor)
            return
        if not self.crop_mode or not self._drag:
            return super().mouseReleaseEvent(e)
        self._drag = None
        r = self._rect
        if r is None or r.width() < 8 or r.height() < 8:
            self._rect = None
            self.crop_changed.emit(None)
        else:
            self.crop_changed.emit((int(r.left()), int(r.top()), int(r.right()), int(r.bottom())))
        self._update_overlay()

    def _clamp(self, p: QPointF) -> QPointF:
        b = self.scene().sceneRect()
        return QPointF(min(max(p.x(), 0), b.width()), min(max(p.y(), 0), b.height()))

    def _update_overlay(self) -> None:
        show = self._rect is not None
        self.frame.setVisible(show)
        self.shade.setVisible(show)
        if not show:
            return
        self.frame.setRect(self._rect)
        path = QPainterPath()
        path.addRect(self.scene().sceneRect())
        inner = QPainterPath()
        inner.addRect(self._rect)
        self.shade.setPath(path.subtracted(inner))
